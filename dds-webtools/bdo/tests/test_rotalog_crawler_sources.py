import unittest

from bdo.services.rotalog_crawler_service import (
    CrawlerRotalog,
    URL_EQUIPES,
    URL_LISTAGEM_EVENTOS,
)


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.posts = []

    def get(self, url, **kwargs):
        return FakeResponse(
            '<input name="javax.faces.ViewState" value="initial">'
        )

    def post(self, url, data=None, **kwargs):
        self.posts.append(url)
        if url == URL_EQUIPES:
            return FakeResponse(
                '<input name="javax.faces.ViewState" value="equipes">'
                '<div id="form:tbEquipes"><table>'
                '<thead><tr><th>Veículo</th><th>Data Referência - Turno</th></tr></thead>'
                '<tbody><tr><td>E1234</td><td>08/09/2026 08:00 - 17:00</td></tr></tbody>'
                '</table></div>'
                '<script>widget_form_tbEquipes rowCount:1</script>'
            )
        return FakeResponse(
            '<input name="javax.faces.ViewState" value="eventos">'
            '<div id="form:tbListagemEventos"><table>'
            '<thead><tr><th>Veículo</th><th>Protocolo</th><th>Inicio Deslo</th></tr></thead>'
            '<tbody><tr><td>E1234</td><td>1234567</td><td>08/09/2026 08:10</td></tr></tbody>'
            '</table></div>'
            '<script>widget_form_tbListagemEventos rowCount:1</script>'
        )


class CrawlerSourceTests(unittest.TestCase):
    def test_usa_paginas_independentes_para_equipes_e_eventos(self):
        crawler = CrawlerRotalog("usuario", "senha")
        session = FakeSession()
        crawler._criar_sessao_autenticada = lambda: session

        equipes, eventos = crawler._raspar_bloco("08/09/2026", "08/09/2026")

        self.assertEqual([URL_EQUIPES, URL_LISTAGEM_EVENTOS], session.posts)
        self.assertEqual("E1234", equipes.iloc[0]["Veículo"])
        self.assertEqual("1234567", eventos.iloc[0]["Protocolo"])


if __name__ == "__main__":
    unittest.main()
