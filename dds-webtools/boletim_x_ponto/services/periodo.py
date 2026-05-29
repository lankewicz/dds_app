# d:\programas\DDS\dds-webtools\boletim_x_ponto\services\periodo.py
from datetime import datetime as dt, date, timedelta
import calendar

def mes_inicio_fim(data_ini: date, data_fim: date):
    """1º dia do mês de data_ini até último dia do mês de data_fim."""
    ini = date(data_ini.year, data_ini.month, 1)
    last = calendar.monthrange(data_fim.year, data_fim.month)[1]
    fim = date(data_fim.year, data_fim.month, last)
    return ini, fim

def iter_dias(d1: date, d2: date):
    cur = d1
    while cur <= d2:
        yield cur
        cur += timedelta(days=1)

def datas_formatadas_do_mes(data_ini: date, data_fim: date):
    """Lista ['dd/mm/aaaa', ...] cobrindo do 1º dia (ini) ao último (fim)."""
    ini, fim = mes_inicio_fim(data_ini, data_fim)
    return [d.strftime("%d/%m/%Y") for d in iter_dias(ini, fim)]
