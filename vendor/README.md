# vendor/

## byedpi

DPI bypass proxy'si (`ciadpi`). Kaynak: https://github.com/hufrea/byedpi
Sürüm: v0.17.3-38-gba53229 · Lisans: MIT (bkz. `byedpi/LICENSE`)

**Neden burada:** `docker/proxy.Dockerfile` eskiden bu depoyu derleme sırasında
GitHub'dan klonluyordu. GitHub'a erişilemeyen ağlarda imaj derlenemiyordu.
Kaynak burada olduğu için derleme artık yalnızca Alpine paket deposuna ihtiyaç
duyuyor; GitHub'a hiç çıkmıyor.

Güncellemek için: bu klasörün içeriğini yeni sürümle değiştirin
(derleme çıktıları `*.o`, `ciadpi`, `dist/` hariç).

## Depoda tutulmayanlar

`vendor/python/`, `vendor/node/` ve `vendor/wheels/` **git'e girmiyor** (~49 MB,
hepsi yeniden indirilebilir). Çevrimdışı Windows paketi üretmeden önce:

```bash
./scripts/vendor-indir.sh
```

`byedpi` ve `byedpi-win` depoda kalır: kaynakları GitHub ve bu projenin hedef
ağlarında GitHub'a erişilemiyor — vendorlamanın sebebi zaten bu.
