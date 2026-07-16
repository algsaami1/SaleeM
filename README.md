# SaleeM — محلل شارت الذهب

تطبيق FastAPI يرفع صورة شارت، يستخدم ChatGPT لإرجاع تحليل منظم، ثم يرسل تعليمات الرسم إلى Gemini لإنتاج نسخة مشروحة.

## متغيرات Railway المطلوبة

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`

## متغيرات اختيارية

- `OPENAI_MODEL` والقيمة الافتراضية `gpt-4.1-mini`
- `GEMINI_IMAGE_MODEL` والقيمة الافتراضية `gemini-2.5-flash-image`

## التشغيل

Railway سيبني التطبيق من `Dockerfile` ويشغله تلقائيًا. رابط فحص الصحة:

`/health`

التطبيق تعليمي، ولا يضمن نتائج التداول.
