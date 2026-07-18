(() => {
  const form = document.getElementById('analysis-form');
  const fileInput = document.getElementById('image-input');
  const fileName = document.getElementById('file-name');
  const dropZone = document.getElementById('drop-zone');
  const processingCard = document.getElementById('processing-card');
  const progressRing = document.getElementById('progress-ring');
  const progressValue = document.getElementById('progress-value');
  const analysisCount = document.getElementById('analysis-count');
  const steps = processingCard ? [...processingCard.querySelectorAll('.steps span')] : [];
  const resultImage = document.getElementById('result-image');
  const saveImageButton = document.getElementById('save-image-button');
  const shareImageButton = document.getElementById('share-image-button');
  const resultActionStatus = document.getElementById('result-action-status');
  const feedbackCard = document.getElementById('feedback-card');
  const feedbackForm = document.getElementById('feedback-form');
  const feedbackNotes = document.getElementById('feedback-notes');
  const feedbackCount = document.getElementById('feedback-count');
  const feedbackStatus = document.getElementById('feedback-status');
  const ratingInput = document.getElementById('rating-value');
  const ratingStars = [...document.querySelectorAll('.rating-star')];
  const supportDeveloper = document.getElementById('support-developer');
  const ATTEMPT_KEY = 'saleem_analysis_attempts_v2';
  const PENDING_KEY = 'saleem_analysis_pending_v2';
  const FEEDBACK_KEY = 'saleem_feedback_prepared_v1';

  const getStoredNumber = (key) => {
    try {
      return Number.parseInt(window.localStorage.getItem(key) || '0', 10) || 0;
    } catch {
      return 0;
    }
  };

  const setStoredValue = (key, value) => {
    try {
      window.localStorage.setItem(key, String(value));
    } catch {
      // يستمر التطبيق حتى إذا كان التخزين المحلي محظورًا.
    }
  };

  const removeStoredValue = (key) => {
    try {
      window.localStorage.removeItem(key);
    } catch {
      // لا شيء.
    }
  };

  const showAnalysisCount = () => {
    if (analysisCount) analysisCount.textContent = String(getStoredNumber(ATTEMPT_KEY));
  };

  const updateFileName = () => {
    if (fileName) fileName.textContent = fileInput?.files?.[0]?.name || 'لم يتم اختيار صورة';
  };

  fileInput?.addEventListener('change', updateFileName);

  if (dropZone) {
    ['dragenter', 'dragover'].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.add('dragging');
      });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
      dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropZone.classList.remove('dragging');
      });
    });

    dropZone.addEventListener('drop', (event) => {
      const files = event.dataTransfer?.files;
      if (!files?.length || !fileInput) return;
      const dt = new DataTransfer();
      dt.items.add(files[0]);
      fileInput.files = dt.files;
      updateFileName();
    });
  }

  form?.addEventListener('submit', (event) => {
    if (!fileInput?.files?.length) {
      event.preventDefault();
      dropZone?.animate(
        [
          { transform: 'translateX(0)' },
          { transform: 'translateX(-6px)' },
          { transform: 'translateX(6px)' },
          { transform: 'translateX(0)' },
        ],
        { duration: 340 }
      );
      return;
    }

    setStoredValue(PENDING_KEY, 1);
    if (!processingCard || !progressRing || !progressValue) return;

    processingCard.hidden = false;
    progressRing.style.setProperty('--progress', '1');
    progressValue.textContent = '1%';
    processingCard.scrollIntoView({ behavior: 'smooth', block: 'center' });

    let progress = 1;
    let currentStep = 0;
    const timer = window.setInterval(() => {
      progress = Math.min(96, progress + Math.max(1, Math.round((97 - progress) / 18)));
      progressRing.style.setProperty('--progress', String(progress));
      progressValue.textContent = `${progress}%`;

      const nextStep = Math.min(4, Math.floor(progress / 20));
      if (nextStep !== currentStep) {
        currentStep = nextStep;
        steps.forEach((step, index) => step.classList.toggle('active', index <= currentStep));
      }

      if (progress >= 96) window.clearInterval(timer);
    }, 260);
  });

  const hasResult = document.body.dataset.hasResult === 'true';
  const hasError = Boolean(document.querySelector('.error-card'));
  if (hasResult && getStoredNumber(PENDING_KEY) === 1) {
    setStoredValue(ATTEMPT_KEY, getStoredNumber(ATTEMPT_KEY) + 1);
    removeStoredValue(PENDING_KEY);
  } else if (hasError) {
    removeStoredValue(PENDING_KEY);
  }
  showAnalysisCount();

  const attempts = getStoredNumber(ATTEMPT_KEY);
  const feedbackAlreadyPrepared = getStoredNumber(FEEDBACK_KEY) === 1;
  if (feedbackCard && hasResult && attempts >= 4 && !feedbackAlreadyPrepared) {
    feedbackCard.hidden = false;
  }

  const imageFile = () => {
    if (!resultImage?.src) throw new Error('الصورة غير متاحة.');
    const name = `SaleeM-XAUUSD-M5-${Date.now()}.png`;

    // النتيجة تصل كـ data URL؛ تحويلها محليًا يحافظ على صلاحية ضغطة المستخدم
    // المطلوبة لفتح نافذة المشاركة في Safari على الآيفون.
    if (resultImage.src.startsWith('data:')) {
      const [header, encoded] = resultImage.src.split(',', 2);
      const mime = header.match(/^data:([^;]+)/)?.[1] || 'image/png';
      const binary = window.atob(encoded);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      return new File([bytes], name, { type: mime });
    }

    return fetch(resultImage.src).then((response) => {
      if (!response.ok) throw new Error('تعذر تجهيز الصورة.');
      return response.blob();
    }).then((blob) => new File([blob], name, { type: blob.type || 'image/png' }));
  };

  const canShareFile = (file) => {
    if (!navigator.share) return false;
    if (typeof navigator.canShare !== 'function') return true;
    try {
      return navigator.canShare({ files: [file] });
    } catch {
      return false;
    }
  };

  const downloadFile = (file) => {
    const url = URL.createObjectURL(file);
    const link = document.createElement('a');
    link.href = url;
    link.download = file.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
  };

  saveImageButton?.addEventListener('click', async () => {
    if (resultActionStatus) resultActionStatus.textContent = 'جاري تجهيز الصورة...';
    saveImageButton.disabled = true;
    try {
      const prepared = imageFile();
      const file = prepared instanceof Promise ? await prepared : prepared;
      const isiPhoneOrIPad = /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

      if (isiPhoneOrIPad && canShareFile(file)) {
        if (resultActionStatus) resultActionStatus.textContent = 'اختر «حفظ الصورة» من القائمة لتظهر في الاستديو.';
        await navigator.share({ files: [file], title: 'تحليل SaleeM' });
      } else {
        downloadFile(file);
        if (resultActionStatus) resultActionStatus.textContent = 'تم تنزيل الصورة على الجهاز.';
      }
    } catch (error) {
      if (error?.name !== 'AbortError' && resultActionStatus) {
        resultActionStatus.textContent = 'تعذر الحفظ. استخدم زر المشاركة ثم اختر حفظ الصورة.';
      }
    } finally {
      saveImageButton.disabled = false;
    }
  });

  shareImageButton?.addEventListener('click', async () => {
    if (resultActionStatus) resultActionStatus.textContent = 'جاري تجهيز المشاركة...';
    shareImageButton.disabled = true;
    try {
      const prepared = imageFile();
      const file = prepared instanceof Promise ? await prepared : prepared;
      if (canShareFile(file)) {
        await navigator.share({
          files: [file],
          title: 'تحليل SaleeM للذهب',
          text: 'تحليل XAUUSD على فريم خمس دقائق بواسطة SaleeM.',
        });
        if (resultActionStatus) resultActionStatus.textContent = 'تم فتح خيارات المشاركة.';
      } else {
        downloadFile(file);
        if (resultActionStatus) resultActionStatus.textContent = 'المشاركة غير مدعومة؛ تم تنزيل الصورة بدلًا منها.';
      }
    } catch (error) {
      if (error?.name !== 'AbortError' && resultActionStatus) {
        resultActionStatus.textContent = 'تعذر فتح المشاركة على هذا المتصفح.';
      }
    } finally {
      shareImageButton.disabled = false;
    }
  });

  const selectRating = (rating) => {
    const selected = Number(rating);
    if (ratingInput) ratingInput.value = String(selected);
    ratingStars.forEach((star) => {
      const active = Number(star.dataset.rating) <= selected;
      star.classList.toggle('selected', active);
      star.textContent = active ? '★' : '☆';
      star.setAttribute('aria-checked', active && Number(star.dataset.rating) === selected ? 'true' : 'false');
    });
    if (feedbackStatus) feedbackStatus.textContent = '';
  };

  ratingStars.forEach((star) => {
    star.addEventListener('click', () => selectRating(star.dataset.rating));
  });

  feedbackNotes?.addEventListener('input', () => {
    if (feedbackCount) feedbackCount.textContent = String(feedbackNotes.value.length);
  });

  feedbackForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    const rating = Number(ratingInput?.value || 0);
    if (!rating) {
      if (feedbackStatus) feedbackStatus.textContent = 'اختر عدد النجوم أولًا.';
      ratingStars[0]?.focus();
      return;
    }

    const notes = feedbackNotes?.value.trim() || 'لا توجد ملاحظات مكتوبة.';
    const support = supportDeveloper?.checked ? 'نعم، أرغب في دعم المطور.' : 'ليس حاليًا.';
    const subject = `تقييم تطبيق SaleeM - ${rating} من 5`;
    const body = [
      'تقييم تطبيق SaleeM',
      `التقييم: ${rating} من 5`,
      `دعم المطور: ${support}`,
      '',
      'الملاحظات والاقتراحات:',
      notes,
    ].join('\n');

    setStoredValue(FEEDBACK_KEY, 1);
    if (feedbackStatus) feedbackStatus.textContent = 'تم تجهيز رسالة البريد. اضغط إرسال داخل تطبيق البريد.';
    window.location.href = `mailto:algsaami@gmail.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  });
})();
