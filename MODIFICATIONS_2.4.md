# تعديلات SaleeM 2.4

## ما تم تنفيذه

- إضافة `app/services/market_data.py` لجلب `M5` و`M15` و`H1` و`H4` من Twelve Data.
- حفظ البيانات في ملف JSON واحد بدل طلب الفريمات الأربعة مع كل تحليل.
- تحديث كل فريم بصورة مستقلة:
  - M5: 4 دقائق.
  - M15: 14 دقيقة.
  - H1: 55 دقيقة.
  - H4: 4 ساعات.
- استبدال بيانات الفريم المنتهي فقط، دون تراكم ملفات قديمة.
- استخدام نسخة محفوظة قديمة مؤقتًا إذا تعطل مزود البيانات، مع تخفيض قوة الاحتمال.
- دمج اتجاه الفريمات العليا مع قرار M5 في `analyzer.py`.
- عرض ملخص `H4` و`H1` و`M15` داخل صورة النتيجة.
- إضافة `.env.example` وإرشادات Railway Volume.
- إضافة اختبارات للتخزين الملفي والتحديث الجزئي.

## متغيرات Railway الإلزامية

```env
OPENAI_API_KEY=...
TWELVE_DATA_API_KEY=...
```

## مسار التخزين

بدون Volume:

```env
MARKET_DATA_CACHE_PATH=/tmp/saleem_market_data_cache.json
```

مع Railway Volume مركب على `/data`:

```env
MARKET_DATA_CACHE_PATH=/data/saleem_market_data_cache.json
```

## التحقق

تم تشغيل الاختبارات بعد التعديل: `10 passed`.
