(() => {
  const form = document.getElementById('analysis-form');
  const fileInput = document.getElementById('image-input');
  const fileName = document.getElementById('file-name');
  const dropZone = document.getElementById('drop-zone');
  const processingCard = document.getElementById('processing-card');
  const progressRing = document.getElementById('progress-ring');
  const progressCircle = document.getElementById('progress-circle');
  const progressValue = document.getElementById('progress-value');
  const analyzeButton = document.getElementById('analyze-button');
  const steps = processingCard ? [...processingCard.querySelectorAll('.steps span')] : [];
  const resultImage = document.getElementById('result-image');
  const saveImageButton = document.getElementById('save-image-button');
  const shareImageButton = document.getElementById('share-image-button');
  const resultActionStatus = document.getElementById('result-action-status');
  const axisRetryButton = document.getElementById('axis-retry-button');

  const tradeFeedbackForm = document.getElementById('trade-feedback-form');
  const tradeStatus = document.getElementById('trade-feedback-status');
  const tradeResultInput = document.getElementById('trade-result-value');
  const tradeResultOptions = [...document.querySelectorAll('.trade-result-option')];
  const ratingInput = document.getElementById('rating-value');
  const ratingStars = [...document.querySelectorAll('.rating-star')];
  const notesForm = document.getElementById('notes-form');
  const feedbackNotes = document.getElementById('feedback-notes');
  const feedbackCount = document.getElementById('feedback-count');
  const notesStatus = document.getElementById('notes-status');

  const summaryGauge = document.getElementById('summary-gauge');
  const summaryAverageRating = document.getElementById('summary-average-rating');
  const summaryRatingCount = document.getElementById('summary-rating-count');
  const summarySuccessRate = document.getElementById('summary-success-rate');
  const summarySuccessRateInline = document.getElementById('summary-success-rate-inline');
  const summaryFailureRateInline = document.getElementById('summary-failure-rate-inline');
  const summarySuccessBar = document.getElementById('summary-success-bar');
  const summaryTotalTrades = document.getElementById('summary-total-trades');
  const summaryWins = document.getElementById('summary-wins');
  const summaryLosses = document.getElementById('summary-losses');
  const summaryOpenTrades = document.getElementById('summary-open-trades');
  const summaryStars = document.getElementById('summary-stars');


  const updateFileName = () => {
    if (fileName) fileName.textContent = fileInput?.files?.[0]?.name || 'لم يتم اختيار صورة';
  };

  const handleSelectedFile = () => {
    updateFileName();
  };

  fileInput?.addEventListener('change', handleSelectedFile);

  axisRetryButton?.addEventListener('click', () => {
    const uploadCard = document.querySelector('.upload-card');
    uploadCard?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => fileInput?.click(), 260);
  });

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
      handleSelectedFile();
    });
  }

  const updateProcessingSteps = (progress) => {
    if (!steps.length) return;
    const currentStep = Math.min(steps.length - 1, Math.floor(progress / 20));
    steps.forEach((step, index) => {
      step.classList.remove('done', 'current');
      if (index < currentStep) step.classList.add('done');
      else if (index === currentStep) step.classList.add('current');
    });
  };

  const setProgress = (progress) => {
    const safeProgress = Math.max(0, Math.min(100, Number(progress) || 0));
    if (progressCircle) {
      progressCircle.style.strokeDashoffset = String(100 - safeProgress);
    }
    if (progressValue) progressValue.textContent = `${Math.round(safeProgress)}%`;
    updateProcessingSteps(safeProgress);
  };

  const wait = (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  form?.addEventListener('submit', async (event) => {
    event.preventDefault();

    if (!fileInput?.files?.length) {
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

    if (!processingCard || !progressValue) {
      form.submit();
      return;
    }

    processingCard.hidden = false;
    processingCard.classList.add('is-running');
    if (analyzeButton) {
      analyzeButton.disabled = true;
      analyzeButton.textContent = 'جاري التحليل...';
    }

    setProgress(1);
    // نمنح Safari إطارين للرسم قبل بدء الطلب حتى تظهر الحركة فورًا.
    await new Promise((resolve) => window.requestAnimationFrame(() => window.requestAnimationFrame(resolve)));
    processingCard.scrollIntoView({ behavior: 'smooth', block: 'center' });

    let progress = 1;
    const timer = window.setInterval(() => {
      let increment = 1;
      if (progress < 18) increment = 2.8;
      else if (progress < 42) increment = 2.2;
      else if (progress < 68) increment = 1.5;
      else if (progress < 88) increment = 0.8;
      progress = Math.min(96, progress + increment);
      setProgress(progress);
    }, 260);

    try {
      const response = await fetch(form.action || '/analyze', {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch' },
      });
      const html = await response.text();
      window.clearInterval(timer);
      setProgress(100);
      steps.forEach((step) => {
        step.classList.remove('current');
        step.classList.add('done');
      });
      await wait(420);

      // استبدال الصفحة بنتيجة الخادم بعد اكتمال الحركة، مع بقاء الرابط الرئيسي.
      document.open();
      document.write(html);
      document.close();
    } catch (error) {
      window.clearInterval(timer);
      processingCard.classList.remove('is-running');
      if (analyzeButton) {
        analyzeButton.disabled = false;
        analyzeButton.textContent = 'بدء التحليل';
      }
      const message = document.createElement('p');
      message.className = 'processing-error';
      message.textContent = 'تعذر الاتصال بالخادم. تحقق من الإنترنت ثم حاول مرة أخرى.';
      processingCard.appendChild(message);
    }
  });

  const imageFile = () => {
    if (!resultImage?.src) throw new Error('الصورة غير متاحة.');
    const name = `SaleeM-XAUUSD-M5-${Date.now()}.png`;

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

    return fetch(resultImage.src)
      .then((response) => {
        if (!response.ok) throw new Error('تعذر تجهيز الصورة.');
        return response.blob();
      })
      .then((blob) => new File([blob], name, { type: blob.type || 'image/png' }));
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
      const isiPhoneOrIPad = /iPhone|iPad|iPod/i.test(navigator.userAgent)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

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

  const selectTradeResult = (result) => {
    if (tradeResultInput) tradeResultInput.value = result;
    tradeResultOptions.forEach((option) => {
      option.classList.toggle('selected', option.dataset.result === result);
    });
    if (tradeStatus) tradeStatus.textContent = '';
  };

  tradeResultOptions.forEach((option) => {
    option.addEventListener('click', () => selectTradeResult(option.dataset.result || ''));
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
    if (tradeStatus) tradeStatus.textContent = '';
  };

  ratingStars.forEach((star) => {
    star.addEventListener('click', () => selectRating(star.dataset.rating));
  });

  feedbackNotes?.addEventListener('input', () => {
    if (feedbackCount) feedbackCount.textContent = String(feedbackNotes.value.length);
  });

  const paintSummaryStars = (average) => {
    if (!summaryStars) return;
    [...summaryStars.querySelectorAll('span')].forEach((star, index) => {
      star.classList.toggle('filled', index < Math.round(Number(average) || 0));
    });
  };

  const renderSummary = (summary) => {
    if (!summary) return;
    const average = Number(summary.average_rating || 0).toFixed(1);
    if (summaryAverageRating) summaryAverageRating.textContent = average;
    if (summaryRatingCount) summaryRatingCount.textContent = String(summary.rating_count ?? 0);
    if (summarySuccessRate) summarySuccessRate.textContent = `${summary.success_rate ?? 0}%`;
    if (summarySuccessRateInline) summarySuccessRateInline.textContent = `${summary.success_rate ?? 0}%`;
    if (summaryFailureRateInline) summaryFailureRateInline.textContent = `${summary.failure_rate ?? 0}%`;
    if (summarySuccessBar) summarySuccessBar.style.width = `${summary.success_rate ?? 0}%`;
    if (summaryTotalTrades) summaryTotalTrades.textContent = String(summary.total_trades ?? 0);
    if (summaryWins) summaryWins.textContent = String(summary.wins ?? 0);
    if (summaryLosses) summaryLosses.textContent = String(summary.losses ?? 0);
    if (summaryOpenTrades) summaryOpenTrades.textContent = String(summary.open_trades ?? 0);
    if (summaryGauge) summaryGauge.style.setProperty('--summary-progress', String(summary.success_rate ?? 0));
    paintSummaryStars(summary.average_rating || 0);
  };

  if (summaryStars) {
    paintSummaryStars(summaryStars.dataset.average || 0);
  }

  tradeFeedbackForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const tradeResult = tradeResultInput?.value || '';
    const rating = Number(ratingInput?.value || 0);

    if (!tradeResult) {
      if (tradeStatus) tradeStatus.textContent = 'اختر نتيجة الصفقة السابقة أولًا.';
      tradeResultOptions[0]?.focus();
      return;
    }
    if (!rating) {
      if (tradeStatus) tradeStatus.textContent = 'اختر عدد النجوم أولًا.';
      ratingStars[0]?.focus();
      return;
    }

    const submitButton = document.getElementById('trade-feedback-submit');
    if (tradeStatus) tradeStatus.textContent = 'جاري الحفظ...';
    if (submitButton) submitButton.disabled = true;

    try {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trade_result: tradeResult, rating }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'تعذر حفظ التقييم.');
      renderSummary(payload.summary);
      if (tradeStatus) tradeStatus.textContent = payload.message || 'تم حفظ التقييم.';
    } catch (error) {
      if (tradeStatus) tradeStatus.textContent = error.message || 'تعذر حفظ نتيجة الصفقة والتقييم.';
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });

  notesForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = feedbackNotes?.value.trim() || '';
    if (!message) {
      if (notesStatus) notesStatus.textContent = 'اكتب ملاحظاتك أو اقتراحاتك أولًا.';
      feedbackNotes?.focus();
      return;
    }

    const submitButton = notesForm.querySelector('button[type="submit"]');
    if (notesStatus) notesStatus.textContent = 'جاري إرسال الملاحظات...';
    if (submitButton) submitButton.disabled = true;

    try {
      const response = await fetch('/api/notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'تعذر إرسال الملاحظات.');
      if (notesStatus) notesStatus.textContent = payload.message || 'تم إرسال الملاحظات.';
      if (feedbackNotes) feedbackNotes.value = '';
      if (feedbackCount) feedbackCount.textContent = '0';
    } catch (error) {
      if (notesStatus) notesStatus.textContent = error.message || 'تعذر إرسال الملاحظات والاقتراحات.';
    } finally {
      if (submitButton) submitButton.disabled = false;
    }
  });
})();
