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
  const shareResultImage = document.getElementById('share-result-image');
  const saveImageButton = document.getElementById('save-image-button');
  const shareImageButton = document.getElementById('share-image-button');
  const resultActionStatus = document.getElementById('result-action-status');
  const axisRetryButton = document.getElementById('axis-retry-button');
  const captureHelpButton = document.getElementById('capture-help-button');
  const captureHelpModal = document.getElementById('capture-help-modal');

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

  const systemStatusLauncher = document.getElementById('system-status-launcher');
  const systemStatusModal = document.getElementById('system-status-modal');
  const systemStatusClose = document.getElementById('system-status-close');
  const systemCodePanel = document.getElementById('system-code-panel');
  const systemStatusRefresh = document.getElementById('system-status-refresh');
  const systemStatusMessage = document.getElementById('system-status-message');


  const updateFileName = () => {
    if (fileName) fileName.textContent = fileInput?.files?.[0]?.name || 'لم يتم اختيار صورة';
  };

  const handleSelectedFile = () => {
    updateFileName();
  };

  fileInput?.addEventListener('change', handleSelectedFile);

  captureHelpButton?.addEventListener('click', () => {
    if (typeof captureHelpModal?.showModal === 'function') captureHelpModal.showModal();
    else captureHelpModal?.setAttribute('open', '');
  });

  captureHelpModal?.querySelectorAll('[data-close-modal]').forEach((button) => {
    button.addEventListener('click', () => {
      if (typeof captureHelpModal.close === 'function') captureHelpModal.close();
      else captureHelpModal.removeAttribute('open');
    });
  });

  captureHelpModal?.addEventListener('click', (event) => {
    if (event.target !== captureHelpModal) return;
    if (typeof captureHelpModal.close === 'function') captureHelpModal.close();
    else captureHelpModal.removeAttribute('open');
  });

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
    const stepSize = 100 / steps.length;
    const currentStep = Math.min(steps.length - 1, Math.floor(progress / stepSize));
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

    document.body.classList.add('is-analyzing');
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
      document.body.classList.remove('is-analyzing');
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
    const sourceImage = shareResultImage?.src ? shareResultImage : resultImage;
    if (!sourceImage?.src) throw new Error('الصورة غير متاحة.');
    const name = `SaleeM-XAUUSD-M5-${Date.now()}.png`;

    if (sourceImage.src.startsWith('data:')) {
      const [header, encoded] = sourceImage.src.split(',', 2);
      const mime = header.match(/^data:([^;]+)/)?.[1] || 'image/png';
      const binary = window.atob(encoded);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      return new File([bytes], name, { type: mime });
    }

    return fetch(sourceImage.src)
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

  const statusValue = (id, value, tone = '') => {
    const element = document.getElementById(id);
    if (!element) return;
    element.textContent = value ?? '—';
    element.classList.remove('good', 'warn', 'bad', 'info');
    if (tone) element.classList.add(tone);
  };

  const money = (value, digits = 2) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return 'غير مضبوط';
    return `$${Number(value).toFixed(digits)}`;
  };

  const integer = (value) => String(Math.max(0, Math.round(Number(value) || 0)));

  const statusTone = (value) => {
    const text = String(value || '');
    if (text.includes('متصل') || text.includes('يعمل') || text.includes('محدث')) return 'good';
    if (text.includes('غير') || text.includes('خطأ') || text.includes('متوقف')) return 'bad';
    return 'info';
  };

  const renderSystemStatus = (payload) => {
    const app = payload.app || {};
    const users = payload.users || {};
    const market = payload.market || {};
    const openai = payload.openai || {};
    const system = payload.system || {};

    statusValue('status-app-state', app.status, statusTone(app.status));
    statusValue('status-app-version', app.version, 'info');

    statusValue('status-market-state', market.status, statusTone(market.status));
    statusValue('status-market-plan', market.plan || 'Basic', 'info');
    statusValue('status-market-daily', `${integer(market.daily_left)} من ${integer(market.daily_limit)}`, Number(market.daily_left) < 50 ? 'bad' : Number(market.daily_left) < 200 ? 'warn' : 'good');
    const minuteText = market.minute_left === null || market.minute_left === undefined
      ? 'بانتظار أول جلب'
      : `${integer(market.minute_left)} من ${integer(market.minute_limit)}`;
    statusValue('status-market-minute', minuteText, Number(market.minute_left) <= 1 ? 'warn' : 'good');
    statusValue('status-market-refreshes', integer(market.full_refreshes_left), 'info');
    statusValue('status-market-last-fetch', market.last_request_at || 'لم يتم الجلب بعد', market.last_request_at ? 'info' : 'warn');
    const frames = market.frames || {};
    const framesText = ['M5', 'M15', 'H1', 'H4']
      .map((name) => `${name}: ${frames[name]?.status || 'غير متوفر'}`)
      .join(' | ');
    statusValue('status-market-frames', framesText, 'info');

    statusValue('status-users-total', integer(users.total), 'info');
    statusValue('status-users-today', integer(users.today), 'info');
    statusValue('status-users-online', integer(users.online), 'good');
    statusValue('status-analyses-today', integer(users.analyses_today), 'info');

    statusValue('status-openai-state', openai.status, statusTone(openai.status));
    statusValue('status-openai-balance', money(openai.balance_usd), openai.balance_usd === null ? 'warn' : Number(openai.balance_usd) < 1 ? 'bad' : Number(openai.balance_usd) < 5 ? 'warn' : 'good');
    statusValue('status-openai-today', money(openai.used_today_usd, 4), 'info');
    statusValue('status-openai-month', money(openai.used_month_usd, 4), 'info');
    statusValue('status-openai-last', money(openai.last_analysis_usd, 4), 'info');
    statusValue('status-openai-source', openai.cost_source || 'تقديري', openai.cost_source === 'رسمي' ? 'good' : 'warn');

    statusValue('status-cache-state', system.cache, statusTone(system.cache));
    statusValue('status-last-error', system.last_error, system.last_error === 'لا يوجد' ? 'good' : 'bad');
  };

  const loadSystemStatus = async () => {
    if (systemStatusMessage) systemStatusMessage.textContent = 'جاري تحديث البيانات...';
    if (systemStatusRefresh) systemStatusRefresh.disabled = true;
    try {
      const response = await fetch('/api/system-status', { cache: 'no-store' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'تعذر فتح حالة التطبيق.');
      renderSystemStatus(payload);
      if (systemStatusMessage) systemStatusMessage.textContent = 'تم تحديث البيانات.';
    } catch (error) {
      if (systemStatusMessage) systemStatusMessage.textContent = error.message || 'تعذر تحديث البيانات.';
    } finally {
      if (systemStatusRefresh) systemStatusRefresh.disabled = false;
    }
  };

  systemStatusLauncher?.addEventListener('click', () => {
    if (typeof systemStatusModal?.showModal === 'function') systemStatusModal.showModal();
    else systemStatusModal?.setAttribute('open', '');
    loadSystemStatus();
  });

  const closeSystemStatus = () => {
    if (typeof systemStatusModal?.close === 'function') systemStatusModal.close();
    else systemStatusModal?.removeAttribute('open');
  };

  systemStatusClose?.addEventListener('click', closeSystemStatus);
  systemStatusModal?.addEventListener('click', (event) => {
    if (event.target === systemStatusModal) closeSystemStatus();
  });

  systemStatusRefresh?.addEventListener('click', loadSystemStatus);

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

  // v3.46: the original chart image and every overlay move/zoom as one canvas.
  const chartPanViewport = document.getElementById('chart-pan-viewport');
  const chartPanCanvas = document.getElementById('chart-pan-canvas');
  const animationOverlay = document.getElementById('saleem-animation-overlay');
  const animationPlanNode = document.getElementById('saleem-animation-plan');
  const animationReplay = document.getElementById('chart-animation-replay');
  const chartPanHint = document.getElementById('chart-pan-hint');
  const chartZoomIn = document.getElementById('chart-zoom-in');
  const chartZoomOut = document.getElementById('chart-zoom-out');
  const chartZoomReset = document.getElementById('chart-zoom-reset');
  const chartZoomValue = document.getElementById('chart-zoom-value');

  if (chartPanViewport && chartPanCanvas && resultImage) {
    const MIN_ZOOM = 1;
    const MAX_ZOOM = 3.5;
    const ZOOM_STEP = 0.25;
    let zoom = 1;
    let baseHeight = 0;
    let mouseDragging = false;
    let mouseStartX = 0;
    let mouseStartY = 0;
    let mouseStartLeft = 0;
    let mouseStartTop = 0;
    let touchMode = '';
    let touchStartX = 0;
    let touchStartY = 0;
    let touchStartLeft = 0;
    let touchStartTop = 0;
    let pinchStartDistance = 0;
    let pinchStartZoom = 1;
    let pinchContentX = 0;
    let pinchContentY = 0;

    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const hideHint = () => chartPanHint?.classList.add('hidden');
    const updateZoomValue = () => {
      if (chartZoomValue) chartZoomValue.textContent = `${Math.round(zoom * 100)}%`;
    };
    const measureBaseHeight = () => {
      if (zoom === 1 || !baseHeight) baseHeight = Math.max(1, chartPanViewport.clientHeight);
    };
    const applyZoom = (nextZoom, anchorClientX = null, anchorClientY = null) => {
      measureBaseHeight();
      const oldZoom = zoom;
      const newZoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
      if (Math.abs(newZoom - oldZoom) < 0.001) return;

      const rect = chartPanViewport.getBoundingClientRect();
      const localX = anchorClientX == null ? rect.width / 2 : anchorClientX - rect.left;
      const localY = anchorClientY == null ? rect.height / 2 : anchorClientY - rect.top;
      const contentX = chartPanViewport.scrollLeft + localX;
      const contentY = chartPanViewport.scrollTop + localY;
      const scaleRatio = newZoom / oldZoom;

      zoom = newZoom;
      chartPanCanvas.style.height = `${Math.round(baseHeight * zoom)}px`;
      resultImage.style.height = '100%';
      resultImage.style.width = 'auto';
      updateZoomValue();

      requestAnimationFrame(() => {
        chartPanViewport.scrollLeft = contentX * scaleRatio - localX;
        chartPanViewport.scrollTop = contentY * scaleRatio - localY;
      });
      hideHint();
    };
    const scrollToLatest = () => {
      measureBaseHeight();
      chartPanCanvas.style.height = `${baseHeight}px`;
      resultImage.style.height = '100%';
      resultImage.style.width = 'auto';
      chartPanViewport.scrollLeft = chartPanViewport.scrollWidth;
      chartPanViewport.scrollTop = 0;
      updateZoomValue();
    };
    const resetZoom = () => {
      zoom = 1;
      measureBaseHeight();
      chartPanCanvas.style.height = `${baseHeight}px`;
      resultImage.style.height = '100%';
      resultImage.style.width = 'auto';
      updateZoomValue();
      requestAnimationFrame(() => {
        chartPanViewport.scrollLeft = chartPanViewport.scrollWidth;
        chartPanViewport.scrollTop = 0;
      });
      hideHint();
    };

    if (resultImage.complete) scrollToLatest();
    else resultImage.addEventListener('load', scrollToLatest, { once: true });
    window.addEventListener('resize', () => {
      if (zoom === 1) {
        baseHeight = Math.max(1, chartPanViewport.clientHeight);
        chartPanCanvas.style.height = `${baseHeight}px`;
        resultImage.style.height = '100%';
      }
    });

    chartZoomIn?.addEventListener('click', () => applyZoom(zoom + ZOOM_STEP));
    chartZoomOut?.addEventListener('click', () => applyZoom(zoom - ZOOM_STEP));
    chartZoomReset?.addEventListener('click', resetZoom);

    // Desktop / pointer-device drag.
    chartPanViewport.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'touch') return;
      mouseDragging = true;
      mouseStartX = event.clientX;
      mouseStartY = event.clientY;
      mouseStartLeft = chartPanViewport.scrollLeft;
      mouseStartTop = chartPanViewport.scrollTop;
      chartPanViewport.classList.add('dragging');
      chartPanViewport.setPointerCapture?.(event.pointerId);
    });
    chartPanViewport.addEventListener('pointermove', (event) => {
      if (!mouseDragging || event.pointerType === 'touch') return;
      chartPanViewport.scrollLeft = mouseStartLeft - (event.clientX - mouseStartX);
      chartPanViewport.scrollTop = mouseStartTop - (event.clientY - mouseStartY);
      hideHint();
    });
    const endMousePan = () => {
      mouseDragging = false;
      chartPanViewport.classList.remove('dragging');
    };
    chartPanViewport.addEventListener('pointerup', endMousePan);
    chartPanViewport.addEventListener('pointercancel', endMousePan);

    // iPhone/iPad: one finger pans; two fingers pinch-zoom around the midpoint.
    chartPanViewport.addEventListener('touchstart', (event) => {
      if (event.touches.length === 1) {
        touchMode = 'pan';
        touchStartX = event.touches[0].clientX;
        touchStartY = event.touches[0].clientY;
        touchStartLeft = chartPanViewport.scrollLeft;
        touchStartTop = chartPanViewport.scrollTop;
      } else if (event.touches.length >= 2) {
        touchMode = 'pinch';
        const a = event.touches[0];
        const b = event.touches[1];
        pinchStartDistance = Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY) || 1;
        pinchStartZoom = zoom;
        const rect = chartPanViewport.getBoundingClientRect();
        const midX = (a.clientX + b.clientX) / 2 - rect.left;
        const midY = (a.clientY + b.clientY) / 2 - rect.top;
        pinchContentX = chartPanViewport.scrollLeft + midX;
        pinchContentY = chartPanViewport.scrollTop + midY;
      }
      hideHint();
    }, { passive: false });

    chartPanViewport.addEventListener('touchmove', (event) => {
      if (event.touches.length === 1 && touchMode === 'pan') {
        event.preventDefault();
        chartPanViewport.scrollLeft = touchStartLeft - (event.touches[0].clientX - touchStartX);
        chartPanViewport.scrollTop = touchStartTop - (event.touches[0].clientY - touchStartY);
        return;
      }
      if (event.touches.length >= 2) {
        event.preventDefault();
        const a = event.touches[0];
        const b = event.touches[1];
        const distance = Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY) || 1;
        const nextZoom = clamp(pinchStartZoom * (distance / pinchStartDistance), MIN_ZOOM, MAX_ZOOM);
        const oldZoom = zoom;
        if (Math.abs(nextZoom - oldZoom) < 0.008) return;
        const rect = chartPanViewport.getBoundingClientRect();
        const midX = (a.clientX + b.clientX) / 2 - rect.left;
        const midY = (a.clientY + b.clientY) / 2 - rect.top;
        const ratio = nextZoom / oldZoom;
        zoom = nextZoom;
        chartPanCanvas.style.height = `${Math.round(baseHeight * zoom)}px`;
        resultImage.style.height = '100%';
        resultImage.style.width = 'auto';
        updateZoomValue();
        requestAnimationFrame(() => {
          chartPanViewport.scrollLeft = pinchContentX * ratio - midX;
          chartPanViewport.scrollTop = pinchContentY * ratio - midY;
          pinchContentX = chartPanViewport.scrollLeft + midX;
          pinchContentY = chartPanViewport.scrollTop + midY;
        });
      }
    }, { passive: false });

    chartPanViewport.addEventListener('touchend', (event) => {
      if (event.touches.length === 1) {
        touchMode = 'pan';
        touchStartX = event.touches[0].clientX;
        touchStartY = event.touches[0].clientY;
        touchStartLeft = chartPanViewport.scrollLeft;
        touchStartTop = chartPanViewport.scrollTop;
      } else {
        touchMode = '';
      }
    });

    // Trackpad / mouse wheel zoom when Ctrl/Command is held.
    chartPanViewport.addEventListener('wheel', (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      event.preventDefault();
      applyZoom(zoom + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP), event.clientX, event.clientY);
    }, { passive: false });

    const buildScenarioAnimation = () => {
      if (!animationOverlay || !animationPlanNode) return null;
      let plan = null;
      try {
        plan = JSON.parse(animationPlanNode.textContent || '{}');
      } catch {
        return null;
      }
      if (!plan?.enabled || !Array.isArray(plan.points) || plan.points.length < 4) return null;

      const width = Number(plan.width) || resultImage.naturalWidth || 1;
      const height = Number(plan.height) || resultImage.naturalHeight || 1;
      animationOverlay.setAttribute('viewBox', `0 0 ${width} ${height}`);
      animationOverlay.replaceChildren();
      const ns = 'http://www.w3.org/2000/svg';
      const make = (tag, attrs = {}) => {
        const node = document.createElementNS(ns, tag);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
        return node;
      };

      const defs = make('defs');
      const marker = make('marker', {
        id: 'saleem-arrow-head', markerWidth: 10, markerHeight: 10,
        refX: 8.5, refY: 5, orient: 'auto', markerUnits: 'strokeWidth',
      });
      marker.appendChild(make('path', { d: 'M 0 0 L 10 5 L 0 10 z', class: `scenario-arrow-head ${plan.direction === 'up' ? 'up' : 'down'}` }));
      defs.appendChild(marker);
      animationOverlay.appendChild(defs);

      if (plan.pattern?.points?.length >= 3) {
        const pattern = make('polyline', {
          points: plan.pattern.points.map((p) => `${p[0]},${p[1]}`).join(' '),
          class: 'animated-pattern-path', fill: 'none', pathLength: 1,
        });
        animationOverlay.appendChild(pattern);
      }

      if (plan.entry_zone) {
        const zone = plan.entry_zone;
        animationOverlay.appendChild(make('rect', {
          x: zone.x, y: zone.y, width: zone.width, height: zone.height,
          rx: 3, class: `animated-entry-zone ${plan.direction === 'up' ? 'up' : 'down'}`,
        }));
      }

      if (plan.activation) {
        const a = plan.activation;
        animationOverlay.appendChild(make('line', {
          x1: a.x1, y1: a.y, x2: a.x2, y2: a.y,
          class: 'animated-activation-line',
        }));
        const label = make('text', { x: a.x2, y: Math.max(12, a.y - 6), class: 'animated-activation-label', 'text-anchor': 'end' });
        label.textContent = 'BREAK';
        animationOverlay.appendChild(label);
      }

      const pathD = plan.points.map((p, index) => `${index ? 'L' : 'M'} ${p[0]} ${p[1]}`).join(' ');
      const scenarioPath = make('path', {
        d: pathD, fill: 'none',
        class: `animated-scenario-path ${plan.direction === 'up' ? 'up' : 'down'} ${plan.state === 'watch' ? 'watch' : 'confirmed'}`,
        'marker-end': 'url(#saleem-arrow-head)', pathLength: 1,
      });
      animationOverlay.appendChild(scenarioPath);

      if (plan.retest) {
        animationOverlay.appendChild(make('circle', {
          cx: plan.retest.x, cy: plan.retest.y, r: 4.2,
          class: `animated-retest-dot ${plan.direction === 'up' ? 'up' : 'down'}`,
        }));
        const label = make('text', { x: plan.retest.x + 7, y: plan.retest.y - 7, class: 'animated-retest-label' });
        label.textContent = 'RETEST';
        animationOverlay.appendChild(label);
      }

      if (plan.invalidation) {
        const i = plan.invalidation;
        animationOverlay.appendChild(make('line', {
          x1: i.x1, y1: i.y, x2: i.x2, y2: i.y,
          class: 'animated-invalidation-line',
        }));
      }

      const replay = () => {
        animationOverlay.classList.remove('is-running');
        // Restart CSS animations reliably in Safari/iOS.
        void animationOverlay.getBoundingClientRect();
        animationOverlay.classList.add('is-running');
      };
      return replay;
    };

    let replayScenarioAnimation = null;
    const startScenarioAnimation = () => {
      replayScenarioAnimation = buildScenarioAnimation();
      if (replayScenarioAnimation) replayScenarioAnimation();
    };
    if (resultImage.complete) startScenarioAnimation();
    else resultImage.addEventListener('load', startScenarioAnimation, { once: true });
    animationReplay?.addEventListener('click', () => replayScenarioAnimation?.());

    chartPanViewport.addEventListener('scroll', hideHint, { once: true });
    window.setTimeout(() => chartPanHint?.classList.add('hidden'), 5200);
  }

})();
