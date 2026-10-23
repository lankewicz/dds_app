"""Gera somente páginas e assets públicos; nunca exporta usuários ou credenciais."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

from jinja2 import Environment, FileSystemLoader, StrictUndefined

WEBTOOLS = Path(__file__).resolve().parents[1]
REPOSITORY = WEBTOOLS.parent
PUBLIC = REPOSITORY / 'public'
AREAS = {'monitor': 'Monitor de Turnos', 'vexpenses': 'VExpenses',
         'produtividade': 'Monitor de Produtividade', 'bdo': 'Boletim x Ponto',
         'controle_projetos': 'Controle de Projetos'}
ASSET_EXTENSIONS = {'.js', '.css', '.svg', '.png', '.webp', '.jpg', '.jpeg',
                    '.gif', '.ico', '.woff', '.woff2', '.ttf', '.avif'}


def build():
    inputs = [WEBTOOLS / 'templates', WEBTOOLS / 'monitor/static', WEBTOOLS / 'hosting',
              WEBTOOLS / 'controle_projetos/templates', WEBTOOLS / 'controle_projetos/static',
              WEBTOOLS / 'bdo/templates', WEBTOOLS / 'vexpenses/static', WEBTOOLS / 'admin/static']
    digest = hashlib.sha256()
    for directory in inputs:
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                digest.update(str(path.relative_to(WEBTOOLS)).encode())
                digest.update(path.read_bytes())
    version = digest.hexdigest()[:12]
    PUBLIC.mkdir(exist_ok=True)
    assets = [('monitor/static', 'static'), ('controle_projetos/static', 'controle-projetos/static'),
              ('vexpenses/static', 'vexpenses/static'), ('admin/static', 'admin/static'),
              ('hosting', 'static/hosting')]
    for source, target in assets:
        for path in (WEBTOOLS / source).rglob('*'):
            if not path.is_file() or path.suffix.lower() not in ASSET_EXTENSIONS:
                continue
            output = PUBLIC / target / path.relative_to(WEBTOOLS / source)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
    diagnostic = PUBLIC / 'portal' / 'orange-check.html'
    diagnostic.parent.mkdir(exist_ok=True)
    shutil.copyfile(WEBTOOLS / 'hosting/orange-check.html', diagnostic)
    env = Environment(loader=FileSystemLoader(WEBTOOLS), autoescape=True, undefined=StrictUndefined)
    pages = [
        ('/login', 'templates/login.html', 'login', None, {}),
        ('/request-access', 'templates/request_access.html', 'request-access', None, {}),
        ('/', 'templates/landing.html', 'home', '', {}),
        ('/forbidden', 'templates/forbidden.html', 'forbidden', '', {}),
        ('/access-control', 'templates/access_control.html', 'access-control', 'admin',
         {'users': [], 'areas': AREAS, 'csrf_token': '', 'current_is_root': False}),
        ('/monitor', 'templates/index.html', 'monitor', 'monitor', {'page_mode': 'active', 'page_title': 'Monitor de Turnos'}),
        ('/monitor/inativas', 'templates/index.html', 'monitor-inativas', 'monitor', {'page_mode': 'inactive', 'page_title': 'Equipes Inativas'}),
        ('/monitor/lixeira', 'templates/index.html', 'monitor-lixeira', 'monitor', {'page_mode': 'trash', 'page_title': 'Lixeira de Equipes'}),
        ('/boletim-x-ponto', 'bdo/templates/index_boletim.html', 'boletim-x-ponto', 'bdo', {}),
        ('/controle-projetos', 'controle_projetos/templates/index_projetos.html', 'controle-projetos', 'controle_projetos', {}),
        ('/vexpenses', 'vexpenses/static/index.html', 'vexpenses', 'vexpenses', {}),
    ]
    mappings = []
    for route, template, name, permission, extra in pages:
        source = (WEBTOOLS / template).read_text(encoding='utf-8')
        source = re.sub(r'{% if has_permission\("([a-z_]+)"\) %}<a', r'<a data-permission="\1" hidden', source)
        source = source.replace('</a>{% endif %}', '</a>')
        source = source.replace('{{ user_email }}', '<span data-portal-email></span>')
        source = source.replace('{{ user_email if user_email else "Escritório de Engenharia" }}', '<span data-portal-email></span>')
        source = source.replace('{{ request.headers.get("X-Portal-User") or "Local" }}', '<span data-portal-email></span>')
        source = source.replace('{{ permission_name }}', '<span data-denied-permission></span>')
        source = source.replace('{{ revision }}', '<span data-portal-revision></span>') if name != 'vexpenses' else source
        html = env.from_string(source).render(app_title='Portal DDS', app_version=version,
                                              revision=version, **extra)
        if name == 'access-control':
            html = html.replace('const csrfToken="";const currentIsRoot=false;', 'let csrfToken="";let currentIsRoot=false;')
        if permission is not None:
            html = html.replace('<html lang="pt-BR"', f'<html class="portal-loading" data-portal-permission="{permission}" data-portal-page="{name}" lang="pt-BR"', 1)
            html = html.replace('<head>', '<head>\n<style>.portal-loading body{visibility:hidden}[hidden]{display:none!important}</style>'
                                f'\n<script src="/static/hosting/portal.js?v={version}"></script>', 1)
        if '{{' in html or '{%' in html:
            raise ValueError(f'Template não resolvido: {name}')
        output = PUBLIC / 'portal' / f'{name}.html'
        output.parent.mkdir(exist_ok=True)
        output.write_text(html, encoding='utf-8')
        mappings.append({'source': route, 'destination': f'/portal/{name}.html'})
        if route != '/':
            mappings.append({'source': route + '/', 'destination': f'/portal/{name}.html'})
    config_path = REPOSITORY / 'firebase.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    config['hosting']['rewrites'] = mappings + [{'source': '**', 'run': {'serviceId': 'dds-admin-site', 'region': 'us-central1'}}]
    config['hosting']['headers'] = [
        {'source': item['source'], 'headers': [{'key': 'Cache-Control', 'value': 'public,max-age=0,must-revalidate'}]}
        for item in mappings
    ] + [
        {'source': '/portal/**', 'headers': [{'key': 'Cache-Control', 'value': 'public,max-age=0,must-revalidate'}]},
        {'source': '/static/**', 'headers': [{'key': 'Cache-Control', 'value': 'public,max-age=3600'}]},
        {'source': '/{admin,vexpenses,controle-projetos}/static/**', 'headers': [{'key': 'Cache-Control', 'value': 'public,max-age=3600'}]},
    ]
    config['hosting']['predeploy'] = ['python dds-webtools/scripts/build_hosting.py']
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest = {'version': version, 'pages': mappings, 'backend': ['APIs', 'administração DDS dinâmica', 'produtividade', 'relatórios e revisões de projetos']}
    (PUBLIC / 'portal/build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Hosting: {len(pages)} páginas estáticas; versão {version}')
    return manifest


if __name__ == '__main__':
    build()
