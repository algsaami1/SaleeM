(() => {
  const form = document.getElementById('analysis-form');
  const fileInput = document.getElementById('image-input');
  const fileName = document.getElementById('file-name');
  const dropZone = document.getElementById('drop-zone');
  const processingCard = document.getElementById('processing-card');
  const progressRing = document.getElementById('progress-ring');
  const progressValue = document.getElementById('progress-value');
  const steps = processingCard ? [...processingCard.querySelectorAll('.steps span')] : [];
  const feedbackCard = document.getElementById('feedback-card');
  const feedbackForm = document.getElementById('feedback-form');
  const feedbackNotes = document.getElementById('feedback-notes');
  const feedbackCount = document.getElementById('feedback-count');
  const feedbackStatus = document.getElementById('feedback-status');
  const ratingInput = document.getElementById('rating-value');
  const ratingStars = [...document.querySelectorAll('.rating-star')];
  const supportDeveloper = document.getElementById('support-developer');
  const ATTEMPT_KEY = 'saleem_analysis_attempts_v1';
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

  const updateFileName = () => {
    fileName.textContent = fileInput?.files?.[0]?.name || 'لم يتم اختيار صورة';
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
      if (!files?.length) return;
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

    const attempts = getStoredNumber(ATTEMPT_KEY) + 1;
    setStoredValue(ATTEMPT_KEY, attempts);

    processingCard.hidden = false;
    processingCard.scrollIntoView({ behavior: 'smooth', block: 'center' });

    let progress = 2;
    let currentStep = 0;
    const timer = window.setInterval(() => {
      progress = Math.min(94, progress + Math.max(1, Math.round((95 - progress) / 17)));
      progressRing.style.setProperty('--progress', progress);
      progressValue.textContent = `${progress}%`;

      const nextStep = Math.min(4, Math.floor(progress / 19));
      if (nextStep !== currentStep) {
        currentStep = nextStep;
        steps.forEach((step, index) => step.classList.toggle('active', index <= currentStep));
      }

      if (progress >= 94) window.clearInterval(timer);
    }, 240);
  });

  const hasResult = document.body.dataset.hasResult === 'true';
  const attempts = getStoredNumber(ATTEMPT_KEY);
  const feedbackAlreadyPrepared = getStoredNumber(FEEDBACK_KEY) === 1;
  if (feedbackCard && hasResult && attempts >= 4 && !feedbackAlreadyPrepared) {
    feedbackCard.hidden = false;
  }

  const selectRating = (rating) => {
    const selected = Number(rating);
    ratingInput.value = String(selected);
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
