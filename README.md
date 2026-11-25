# Medya İndirme Platformu

URL ile çalışan, **yt-dlp** tabanlı ses / video / görsel indirme uygulaması.
YouTube, Instagram, TikTok, X (Twitter), Facebook, Vimeo, SoundCloud, Reddit
ve 1000+ siteyi destekler.

## Kurulum

```bash
cd media-indirici
pip install -r requirements.txt
```

> `imageio-ffmpeg` paketi statik ffmpeg içerir; MP3 dönüştürme ve video
> birleştirme için ayrıca ffmpeg kurmanıza gerek yoktur.

## Çalıştırma

```bash
python app.py
```

Ardından tarayıcıda açın: **http://127.0.0.1:5000**

## Özellikler

- **URL analizi:** bağlantıyı yapıştırın, başlık, kapak görseli ve mevcut
  kaliteler listelenir.
- **Video indirme:** 1080p, 720p vb. kaliteler; ses/video ayrıksa otomatik
  birleştirilir (MP4).
- **MP3 indirme:** en iyi ses akışını 192 kbps MP3'e dönüştürür.
- **Görsel indirme:** kapak/thumbnail görselini tek tıkla indirir;
  doğrudan görsel URL'leri de analiz edilip indirilebilir.
- **Canlı ilerleme:** yüzde, hız ve kalan süre gösterilir.
- Dosyalar `downloads/` klasörüne iner ve bilgisayara kaydedildikten
  sonra otomatik temizlenir.

## Notlar

- Uygulama **yalnızca localhost (127.0.0.1)** üzerinde dinler; ağa açık değildir.
- YouTube gibi siteler bazen "bot koruması" uygular; bu durumda
  yt-dlp'nin `--cookies-from-browser` desteği ile çerez vermeniz gerekir
  (`app.py` içinde `base_opts()` bölümüne ekleyebilirsiniz).
- Yalnızca size ait olan veya indirilmesine izin verilen içerikleri
  indirin; telif hakkı ve platform kullanım şartlarına uymak sizin
  sorumluluğunuzdadır.
