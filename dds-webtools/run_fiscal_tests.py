import sys
import os
from pathlib import Path

# Configura UTF-8 no stdout para Windows
sys.stdout.reconfigure(encoding='utf-8')

base_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(base_dir / "nfse"))
sys.path.insert(0, str(base_dir))

from tests.test_nfse_fiscal import (
    test_nota_4226_corbelia,
    test_nota_4227_coronel_domingos_soares,
    test_nota_4228_coronel_vivida,
    test_nota_4229_cruz_machado,
    test_nota_4230_cruzeiro_do_iguacu,
    test_nota_4231_diamante_do_sul_isencao_ir,
    test_validacao_discrepancias_reais,
    test_mock_provider
)

def main():
    print("=" * 60)
    print("EXECUTANDO SUÍTE DE TESTES FISCAIS NFS-E (PUTON & DAL MOLIN LTDA)")
    print("=" * 60)

    tests = [
        ("NFS-e 4226 (Corbélia)", test_nota_4226_corbelia),
        ("NFS-e 4227 (Coronel Domingos Soares)", test_nota_4227_coronel_domingos_soares),
        ("NFS-e 4228 (Coronel Vivida)", test_nota_4228_coronel_vivida),
        ("NFS-e 4229 (Cruz Machado)", test_nota_4229_cruz_machado),
        ("NFS-e 4230 (Cruzeiro do Iguaçu)", test_nota_4230_cruzeiro_do_iguacu),
        ("NFS-e 4231 (Diamante do Sul - Isenção IR)", test_nota_4231_diamante_do_sul_isencao_ir),
        ("Detecção de Discrepâncias Reais (Seção 8)", test_validacao_discrepancias_reais),
        ("Conector MockNfseProvider", test_mock_provider),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            print(f"  [OK] SUCCESS: {name}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  [ERRO] FAIL: {name}: {e}")
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"RESULTADO FINAL: {passed} APROVADOS, {failed} FALHAS.")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
