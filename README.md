# VibePlusPlus — Akış deneyi

Akış: bir LLM'in rahat ve az token'la yazması için tasarlanan programlama dili. Deney, aynı işi Python'a göre
daha az token ve daha az hatayla yazdırıp yazdıramadığını ölçer. Protokol: `AKIS_DENEY.md`.

| Klasör | İçerik |
|---|---|
| `spec/` | Modele verilen şartname (`AKIS_SPEC.md`) ve değişiklik kaydı (`CHANGELOG.md`) |
| `akis/` | Akış → Python 3.11 transpiler ve testleri |
| `runtime/` | Üretilen kodun kullandığı çalışma zamanı |
| `bin/akis` | CLI |
| `tasks/`, `harness/`, `results/` | Sonraki fazlar (henüz yok) |

## Kurulum
```bash
python3.11 -m venv .venv-akis
.venv-akis/bin/pip install -r requirements-akis.txt
.venv-akis/bin/python -m pytest -q akis/tests
bin/akis check ornek.aks
bin/akis build ornek.aks -o ornek.py   # çalıştırırken PYTHONPATH'e runtime/ ekleyin
```

## Durum
- Faz 1 (transpiler) bitti, DUR 1 tamam.
- Şartname v0.1: H'nin kararıyla pilottan önce eksikler dolduruldu (`spec/CHANGELOG.md`).
- Şartname v0.2: İngilizceye çevrildi, `use py` izin listesi ve efekt zorunluluğu eklendi (`spec/CHANGELOG.md`).
- Sıradaki: faz 2, 35 görev yazılacak (5 dev + 30 test), DUR 2'de görev listesi H'ye sunulacak.
