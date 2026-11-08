# Akış şartname değişiklikleri

## v0.1 — 2026-11-08 (pilottan önce, H'nin kararıyla)

H: "dilin bütün amacı senin rahat yazabilmen; en rahat yol neyse eksikleri doldur."
Test görevleri henüz yazılmadı; değişiklik hiçbir görev görülmeden yapıldı.

Eklenenler:
- `+= -= *= /= //= %=`, demet açma (`let a, b = ...`, `a, b = b, a`, `for i, x in ...`), `var` üzerinde eleman ataması.
- `break`, `continue`; tek deyimli blok aynı satırda (`if x < 0: return 0`).
- Çağrı biçimleri: `f(x, a)` = `x.f(a)` = `x | f(a)`.
- Akış aşamaları: `max_by K`, `min_by K`, `sort desc`, `avg`, `reverse`. Sözlük üzerinde akış `(anahtar, değer)` verir.
- Değerler: `true/false`, `{x:.2f}` biçimlendirme, negatif indeks, dilim `xs[a:b]`, liste üreteci.
- Olmayan anahtar / aralık dışı indeks hata sayılır, `??` ile yakalanır.
- Yerleşikler: range enumerate zip any all find count append pop keys values items get dict last avg reverse
  sqrt floor ceil log exp, metin: split(s) lstrip rstrip upper lower replace starts_with ends_with chars
  is_digit is_alpha is_space ord chr.
- N2 sadece kullanıcı fonksiyonlarına uygulanır; yerleşikler muaf.
- N1: aynı satırdaki tek deyimli blok (`if c: return x`) seviye sayılmaz. Gerekçe: `for → if → if c: return false`
  gibi doğal bir kalıp bile 3. seviyeye takılıyordu; tek satırlık gövde girinti yaratmaz.
- N1 sınırı 2 → 3. Gerekçe: kısıtsız yazılmış 12 örnek programdan 2'si (ızgara DP: for→for→if, BFS: while→for→if)
  2 seviyeye takıldı; bunları aşmak yardımcı fonksiyon, yani daha çok token ve hata demek.

Değişmeyenler: efektler ve E1, `?`/E2, N2 (kullanıcı fonksiyonları), `T!` denetimi.

Derleyicinin şartnamede yazmadan kabul ettikleri (boşuna hata olmasın diye):
`True/False/None`, tek tırnaklı metin, fn başlığından sonra `:`, `startswith/endswith/isdigit/isalpha/sorted/reversed`
yazımları, `", ".join(xs)` sırası.
