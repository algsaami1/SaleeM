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
  const uploadChartPreview = document.getElementById('upload-chart-preview');
  const uploadChartPlaceholder = document.getElementById('upload-chart-placeholder');
  const uploadChartChange = document.getElementById('upload-chart-change');
  let uploadPreviewUrl = '';

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
    const file = fileInput?.files?.[0];
    if (!file || !uploadChartPreview) return;
    if (uploadPreviewUrl) URL.revokeObjectURL(uploadPreviewUrl);
    uploadPreviewUrl = URL.createObjectURL(file);
    uploadChartPreview.src = uploadPreviewUrl;
    uploadChartPreview.hidden = false;
    if (uploadChartPlaceholder) uploadChartPlaceholder.hidden = true;
    if (uploadChartChange) uploadChartChange.hidden = false;
    dropZone?.classList.add('has-preview');
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

    if (fileInput && !fileInput.files?.length) {
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
        analyzeButton.textContent = 'تحديث الشارت';
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

  // v3.73: fit the full chart first, then enlarge the real canvas for pinch/pan.
  const chartPanViewport = document.getElementById('chart-pan-viewport');
  const chartPanCanvas = document.getElementById('chart-pan-canvas');
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
    let baseWidth = 1;
    let baseHeight = 1;
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
    const chartCard = chartPanViewport.closest('.terminal-chart-card');
    const focused = () => Boolean(chartCard?.classList.contains('chart-focus-v371'));
    const hideHint = () => chartPanHint?.classList.add('hidden');

    const updateZoomValue = () => {
      if (chartZoomValue) chartZoomValue.textContent = `${Math.round(zoom * 100)}%`;
    };

    const naturalRatio = () => {
      const w = Math.max(1, Number(resultImage.naturalWidth) || 16);
      const h = Math.max(1, Number(resultImage.naturalHeight) || 9);
      return w / h;
    };

    const setImportant = (node, name, value) => {
      node.style.setProperty(name, value, 'important');
    };

    const measureBase = () => {
      const ratio = naturalRatio();
      const viewportWidth = Math.max(1, chartPanViewport.clientWidth);

      if (!focused()) {
        baseWidth = viewportWidth;
        baseHeight = Math.max(1, viewportWidth / ratio);
        setImportant(chartPanViewport, 'height', `${Math.round(baseHeight)}px`);
        setImportant(chartPanViewport, 'min-height', '0');
        setImportant(chartPanViewport, 'max-height', 'none');
      } else {
        const viewportHeight = Math.max(1, chartPanViewport.clientHeight);
        if (viewportWidth / viewportHeight > ratio) {
          baseHeight = viewportHeight;
          baseWidth = baseHeight * ratio;
        } else {
          baseWidth = viewportWidth;
          baseHeight = baseWidth / ratio;
        }
      }
    };

    const sizeCanvas = () => {
      const width = Math.max(1, baseWidth * zoom);
      const height = Math.max(1, baseHeight * zoom);

      setImportant(chartPanCanvas, 'width', `${Math.round(width)}px`);
      setImportant(chartPanCanvas, 'height', `${Math.round(height)}px`);
      setImportant(chartPanCanvas, 'min-width', `${Math.round(width)}px`);
      setImportant(chartPanCanvas, 'min-height', `${Math.round(height)}px`);
      setImportant(chartPanCanvas, 'max-width', 'none');
      setImportant(chartPanCanvas, 'max-height', 'none');

      setImportant(resultImage, 'width', '100%');
      setImportant(resultImage, 'height', '100%');
      setImportant(resultImage, 'max-width', 'none');
      setImportant(resultImage, 'max-height', 'none');
      setImportant(resultImage, 'object-fit', 'fill');

      if (zoom <= 1.001) {
        setImportant(chartPanCanvas, 'margin-left', 'auto');
        setImportant(chartPanCanvas, 'margin-right', 'auto');
        setImportant(chartPanCanvas, 'margin-top', focused() ? 'auto' : '0');
        setImportant(chartPanCanvas, 'margin-bottom', focused() ? 'auto' : '0');
      } else {
        setImportant(chartPanCanvas, 'margin', '0');
      }
    };

    const fitChart = () => {
      zoom = 1;
      measureBase();
      sizeCanvas();
      updateZoomValue();
      requestAnimationFrame(() => {
        chartPanViewport.scrollLeft = 0;
        chartPanViewport.scrollTop = 0;
      });
    };

    const applyZoom = (nextZoom, anchorClientX = null, anchorClientY = null) => {
      const oldZoom = zoom;
      const newZoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
      if (Math.abs(newZoom - oldZoom) < 0.001) return;

      const rect = chartPanViewport.getBoundingClientRect();
      const localX = anchorClientX == null ? rect.width / 2 : anchorClientX - rect.left;
      const localY = anchorClientY == null ? rect.height / 2 : anchorClientY - rect.top;
      const contentX = chartPanViewport.scrollLeft + localX;
      const contentY = chartPanViewport.scrollTop + localY;
      const ratio = newZoom / oldZoom;

      zoom = newZoom;
      sizeCanvas();
      updateZoomValue();

      requestAnimationFrame(() => {
        chartPanViewport.scrollLeft = Math.max(0, contentX * ratio - localX);
        chartPanViewport.scrollTop = Math.max(0, contentY * ratio - localY);
      });
      hideHint();
    };

    const resetZoom = () => {
      fitChart();
      hideHint();
    };

    const init = () => {
      fitChart();
    };

    if (resultImage.complete && resultImage.naturalWidth) init();
    else resultImage.addEventListener('load', init, { once: true });

    let resizeTimer = 0;
    const observer = new ResizeObserver(() => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        if (zoom === 1) fitChart();
      }, 50);
    });
    observer.observe(chartPanViewport);

    chartZoomIn?.addEventListener('click', () => applyZoom(zoom + ZOOM_STEP));
    chartZoomOut?.addEventListener('click', () => applyZoom(zoom - ZOOM_STEP));
    chartZoomReset?.addEventListener('click', resetZoom);

    chartPanViewport.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'touch' || zoom <= 1.001) return;
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
      if (event.touches.length === 1 && touchMode === 'pan' && zoom > 1.001) {
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
        if (Math.abs(nextZoom - oldZoom) < 0.006) return;

        const rect = chartPanViewport.getBoundingClientRect();
        const midX = (a.clientX + b.clientX) / 2 - rect.left;
        const midY = (a.clientY + b.clientY) / 2 - rect.top;
        const scaleRatio = nextZoom / oldZoom;

        zoom = nextZoom;
        sizeCanvas();
        updateZoomValue();

        requestAnimationFrame(() => {
          chartPanViewport.scrollLeft = Math.max(0, pinchContentX * scaleRatio - midX);
          chartPanViewport.scrollTop = Math.max(0, pinchContentY * scaleRatio - midY);
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

    chartPanViewport.addEventListener('wheel', (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      event.preventDefault();
      applyZoom(
        zoom + (event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP),
        event.clientX,
        event.clientY,
      );
    }, { passive: false });

    chartPanViewport.addEventListener('scroll', hideHint, { once: true });
    window.setTimeout(() => chartPanHint?.classList.add('hidden'), 5200);
  }


  // V8.0: expire a static M5 result when a newer candle should have closed.
  // This uses no market-data credits and prevents stale guidance on screen.
  const decisionTerminal = document.querySelector('.saleem-terminal[data-decision-valid-until-ms]');
  const staleWarning = document.getElementById('m5-stale-warning');
  if (decisionTerminal) {
    const validUntil = Number(decisionTerminal.dataset.decisionValidUntilMs || 0);
    const applyDecisionFreshness = () => {
      if (!validUntil || Date.now() <= validUntil) return;
      decisionTerminal.classList.add('m5-result-stale');
      if (staleWarning) staleWarning.hidden = false;
    };
    applyDecisionFreshness();
    window.setInterval(applyDecisionFreshness, 15000);
  }

})();
// SALEEM_V81_RESULT_CHART_CARDS_ADDON
(() => {
  const q = (s, root = document) => root.querySelector(s);
  const qa = (s, root = document) => [...root.querySelectorAll(s)];

  const textOf = (el) => (el?.textContent || '').replace(/\s+/g, ' ').trim();

  const smallestPanelContaining = (needle, excluded = '') => {
    const nodes = qa('article, section, div')
      .filter((el) => !excluded || !el.closest(excluded))
      .filter((el) => textOf(el).includes(needle));
    nodes.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
    return nodes[0] || null;
  };

  const firstPrice = (text) => {
    const match = String(text || '').match(/\b(\d{4}(?:\.\d{1,2})?)\b/);
    return match ? match[1] : 'غير متوفر';
  };

  const probability = (text) => {
    const match = String(text || '').match(/(\d{1,3}(?:\.\d+)?)\s*[%٪]/);
    if (!match) return null;
    const n = Math.max(0, Math.min(100, Number(match[1])));
    return Number.isFinite(n) ? n : null;
  };

  const statusLabel = () => {
    const body = textOf(document.body);
    if (body.includes('مشروط شراء')) return 'مشروط شراء';
    if (body.includes('مشروط بيع')) return 'مشروط بيع';
    if (body.includes('مؤكد')) return 'مؤكد';
    return 'مراقبة';
  };

  const nearbyExactValue = (label, root = document) => {
    const candidates = qa('article, section, div, p, span, strong', root)
      .filter((el) => textOf(el).includes(label));
    for (const el of candidates) {
      const t = textOf(el);
      const idx = t.indexOf(label);
      const after = idx >= 0 ? t.slice(idx + label.length) : t;
      const p = firstPrice(after);
      if (p !== 'غير متوفر') return p;
    }
    return 'غير متوفر';
  };

  const targetValue = (sideText) => {
    const t = String(sideText || '');
    const match = t.match(/TP1\s*(\d{4}(?:\.\d{1,2})?)/i);
    return match ? `TP1 ${match[1]}` : 'لا يوجد Target هندسي موثوق';
  };

  const chartHostFor = (image) => {
    if (!image) return null;
    const candidates = [
      image.closest('.chart-card'),
      image.closest('.terminal-chart-card'),
      image.closest('.result-chart'),
      image.closest('.chart-container'),
      image.closest('figure'),
      image.parentElement,
    ].filter(Boolean);
    return candidates.find((el) => !textOf(el).includes('قرار M5 الآن')) || image.parentElement;
  };

  const findFullscreen = (root) => {
    const local = qa('button, a', root || document).find((el) => textOf(el).includes('عرض كامل'));
    if (local) return local;
    return qa('button, a').find((el) => textOf(el).includes('عرض كامل')) || null;
  };

  const ensureChartStage = () => {
    const image = q('#result-image');
    if (!image) return null;

    let stage = q('.v81r-chart-stage');
    if (stage) return stage;

    const oldHost = chartHostFor(image);
    stage = document.createElement('section');
    stage.className = 'v81r-chart-stage';
    stage.setAttribute('aria-label', 'الشارت M5');
    stage.innerHTML = `
      <div class="v81r-chart-head">
        <h3>الشارت M5</h3>
        <span class="v81r-chart-symbol">XAUUSD • M5</span>
      </div>
      <div class="v81r-chart-tools"></div>
      <div class="v81r-chart-air" aria-hidden="true"></div>
      <div class="v81r-chart-media"></div>`;

    if (oldHost?.parentElement) oldHost.insertAdjacentElement('beforebegin', stage);
    else (q('main') || document.body).appendChild(stage);

    const tools = q('.v81r-chart-tools', stage);
    const media = q('.v81r-chart-media', stage);
    const full = findFullscreen(oldHost);
    if (full && tools) tools.appendChild(full);
    if (media) media.appendChild(image);

    // Only hide the old empty shell after its real chart image has been moved.
    if (oldHost && oldHost !== image && oldHost !== stage && !oldHost.contains(image)) {
      oldHost.classList.add('v81r-legacy-chart-shell-hidden');
    }

    return stage;
  };

  const buildResultCard = (side, source) => {
    if (!source) return null;
    const raw = textOf(source);
    const isBuy = side === 'buy';
    const price = firstPrice(raw);
    const prob = probability(raw);
    const title = isBuy ? 'نتيجة الشراء' : 'نتيجة البيع';
    const signal = isBuy ? 'BUY IF' : 'SELL IF';
    const stop = nearbyExactValue('Stop / إلغاء', source) !== 'غير متوفر'
      ? nearbyExactValue('Stop / إلغاء', source)
      : nearbyExactValue('إلغاء / Stop', source);
    const target = targetValue(raw);

    const card = document.createElement('article');
    card.className = `v81r-side-card ${isBuy ? 'v81r-buy-card' : 'v81r-sell-card'}`;
    card.innerHTML = `
      <div class="v81r-side-head">
        <h3>${title}</h3>
        <span class="v81r-state-pill">${statusLabel()}</span>
      </div>
      <div class="v81r-trigger">
        <span>${signal}</span>
        <strong>${price}</strong>
      </div>
      <div class="v81r-plan-row"><span>إلغاء / Stop</span><strong>${stop}</strong></div>
      <div class="v81r-target-copy">${target}</div>
      <p class="v81r-reason">${target.startsWith('TP1') ? 'الهدف معروض من بيانات النتيجة الحالية.' : 'لن يصنع SaleeM هدفًا هندسيًا غير متوفر في النتيجة الحالية.'}</p>
      ${prob === null ? '' : `
        <div class="v81r-prob">
          <span>الترجيح ${prob.toFixed(1)}%</span>
          <div class="v81r-prob-bar" style="--v81r-prob:${prob}%"><i></i></div>
        </div>`}`;
    return card;
  };

  const ensureResultCards = (stage) => {
    if (!stage || q('.v81r-results-grid')) return;
    const buySource = smallestPanelContaining('شراء إذا', '.v81r-results-grid');
    const sellSource = smallestPanelContaining('بيع إذا', '.v81r-results-grid');
    if (!buySource && !sellSource) return;

    const grid = document.createElement('section');
    grid.className = 'v81r-results-grid';
    grid.setAttribute('aria-label', 'نتائج الشراء والبيع');

    const buy = buildResultCard('buy', buySource);
    const sell = buildResultCard('sell', sellSource);
    if (buy) grid.appendChild(buy);
    if (sell) grid.appendChild(sell);
    stage.insertAdjacentElement('afterend', grid);

    // Preserve the original elements in DOM/code but hide only the duplicated visual cards.
    [buySource, sellSource].filter(Boolean).forEach((el) => el.classList.add('v81r-legacy-side-hidden'));
  };

  const openExistingRules = () => {
    const button = qa('button, summary, a').find((el) => textOf(el).includes('عرض القواعد'));
    if (button) {
      try { button.click(); } catch (_) {}
      return;
    }
    const details = qa('details').find((el) => textOf(el).includes('القواعد'));
    if (details) details.open = true;
  };

  const ensureRulesCard = () => {
    if (q('.v81r-rules-card')) return;
    const source = smallestPanelContaining('القواعد التي بُنيت عليها النتيجة', '.v81r-rules-card');
    const sourceText = textOf(source || document.body);
    const okMatch = sourceText.match(/(\d+)\s*متحقق/);
    const waitMatch = sourceText.match(/(\d+)\s*(?:انتظار|قيد الانتظار)/);

    const card = document.createElement('section');
    card.className = 'v81r-rules-card';
    card.innerHTML = `
      <h3>القواعد التي بُنيت عليها النتيجة</h3>
      <div class="v81r-rules-stats">
        <span class="v81r-rule-chip ok">${okMatch ? `✓ ${okMatch[1]} متحقق` : '✓ مراجعة القواعد'}</span>
        <span class="v81r-rule-chip wait">${waitMatch ? `! ${waitMatch[1]} انتظار` : '! حالات الانتظار حسب النتيجة'}</span>
      </div>
      <button class="v81r-rules-button" type="button">عرض القواعد</button>`;
    q('.v81r-results-grid')?.insertAdjacentElement('afterend', card);
    q('.v81r-rules-button', card)?.addEventListener('click', openExistingRules);
  };

  const apply = () => {
    const stage = ensureChartStage();
    if (!stage) return false;
    ensureResultCards(stage);
    ensureRulesCard();
    return true;
  };

  const boot = () => {
    if (apply()) return;
    const observer = new MutationObserver(() => {
      if (apply()) observer.disconnect();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    [120, 400, 900, 1800, 3200].forEach((ms) => setTimeout(() => {
      if (apply()) observer.disconnect();
    }, ms));
    setTimeout(() => observer.disconnect(), 6000);
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();

// SALEEM_V81_WIDE_RESULT_RULE_LINK_POLISH
(() => {
  const q = (s, root = document) => root.querySelector(s);
  const qa = (s, root = document) => [...root.querySelectorAll(s)];
  const tx = (el) => (el?.textContent || '').replace(/\s+/g, ' ').trim();

  const smallestContaining = (needle, root = document, exclude = '') => {
    const nodes = qa('article,section,div', root)
      .filter((el) => (!exclude || !el.closest(exclude)) && tx(el).includes(needle));
    nodes.sort((a,b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
    return nodes[0] || null;
  };

  const leafContaining = (needle, root = document) => {
    return qa('h1,h2,h3,h4,p,span,strong,b,small', root)
      .filter((el) => tx(el).includes(needle))
      .sort((a,b) => a.children.length - b.children.length)[0] || null;
  };

  const decorateDecision = () => {
    const decisionText = leafContaining('قرار M5 الآن') || leafContaining('قرار الـ M5 الآن');
    if (!decisionText) return null;
    let box = decisionText.closest('article,section,div');
    for (let i = 0; box && i < 5; i++, box = box.parentElement) {
      const t = tx(box);
      if (t.includes('الأفضلية') && (t.includes('لا دخول الآن') || t.includes('مشروط'))) break;
    }
    if (!box) return null;
    box.classList.add('v81p-wide-decision');

    const title = leafContaining('لا دخول الآن', box) || leafContaining('مشروط', box);
    title?.classList.add('v81p-decision-title');
    leafContaining('السوق مباشر', box)?.classList.add('v81p-decision-live');
    qa('p,span,small', box).forEach((el) => {
      if (!el.classList.contains('v81p-decision-live')) el.classList.add('v81p-decision-muted');
    });
    const pref = smallestContaining('الأفضلية', box);
    pref?.classList.add('v81p-preference-box');
    return box;
  };

  const decorateSummaryCards = () => {
    const next = smallestContaining('المحطة التالية');
    next?.classList.add('v81p-next-station');

    [
      ['M5 الآن', 'blue'],
      ['الهيكل السابق', 'green'],
      ['التأكيد', 'orange'],
      ['الموقع', 'orange'],
    ].forEach(([needle, tone]) => {
      const card = smallestContaining(needle);
      if (!card || card.closest('.v81r-chart-stage') || card.closest('.v81r-results-grid')) return;
      card.classList.add('v81p-mini-card', `v81p-mini-card-${tone}`);
    });
  };

  const shortValue = (needle) => {
    const el = smallestContaining(needle);
    if (!el) return '';
    let s = tx(el).replace(needle, '').replace(/\s+/g, ' ').trim();
    return s.slice(0, 52);
  };

  const status = () => {
    const body = tx(document.body);
    if (body.includes('مشروط شراء')) return 'مشروط شراء';
    if (body.includes('مشروط بيع')) return 'مشروط بيع';
    if (body.includes('مؤكد')) return 'مؤكد';
    return 'مراقبة';
  };

  const existingRuleCounts = () => {
    const src = smallestContaining('القواعد التي بُنيت عليها النتيجة');
    const s = tx(src || document.body);
    const ok = s.match(/(\d+)\s*متحقق/);
    const wait = s.match(/(\d+)\s*(?:انتظار|قيد الانتظار)/);
    return { ok: ok ? ok[1] : '', wait: wait ? wait[1] : '' };
  };

  const ensureLogicStrip = () => {
    if (q('.v81p-logic-strip')) return;
    const chart = q('.v81r-chart-stage');
    if (!chart) return;
    const counts = existingRuleCounts();
    const chips = [];
    chips.push(`<span class="v81p-logic-chip state">الحالة: ${status()}</span>`);
    const m5 = shortValue('M5 الآن');
    const structure = shortValue('الهيكل السابق');
    const confirm = shortValue('التأكيد');
    if (m5) chips.push(`<span class="v81p-logic-chip">M5: ${m5}</span>`);
    if (structure) chips.push(`<span class="v81p-logic-chip">الهيكل: ${structure}</span>`);
    if (confirm) chips.push(`<span class="v81p-logic-chip wait">التأكيد: ${confirm}</span>`);
    if (counts.ok) chips.push(`<span class="v81p-logic-chip ok">${counts.ok} قاعدة متحققة</span>`);
    if (counts.wait) chips.push(`<span class="v81p-logic-chip wait">${counts.wait} انتظار</span>`);

    const strip = document.createElement('section');
    strip.className = 'v81p-logic-strip';
    strip.setAttribute('aria-label', 'ربط النتيجة بالقواعد');
    strip.innerHTML = `
      <div class="v81p-logic-head">
        <strong>ملخص سبب النتيجة</strong>
        <span>من القواعد والبيانات الظاهرة نفسها</span>
      </div>
      <div class="v81p-logic-chips">${chips.join('')}</div>`;
    chart.insertAdjacentElement('beforebegin', strip);
  };

  const decorateReadiness = () => {
    const cards = qa('.v81r-side-card');
    if (!cards.length) return;
    let needsNote = false;
    cards.forEach((card) => {
      if (q('.v81p-readiness', card)) return;
      const s = tx(card);
      const missingStop = /Stop|إلغاء/.test(s) && s.includes('غير متوفر');
      const missingTarget = s.includes('لا يوجد Target هندسي موثوق');
      if (!missingStop && !missingTarget) return;
      needsNote = true;
      const note = document.createElement('div');
      note.className = 'v81p-readiness';
      note.textContent = missingStop
        ? 'الخطة غير مكتملة: لا يوجد Stop / إلغاء صالح في النتيجة الحالية.'
        : 'الهدف الهندسي غير متوفر؛ تبقى الخطة انتظارًا ولا يُنشأ هدف افتراضي.';
      const prob = q('.v81r-prob', card);
      (prob || card).insertAdjacentElement(prob ? 'beforebegin' : 'beforeend', note);
    });

    if (needsNote && !q('.v81p-execution-note')) {
      const grid = q('.v81r-results-grid');
      if (!grid) return;
      const note = document.createElement('div');
      note.className = 'v81p-execution-note';
      note.textContent = 'الترجيح يشرح السيناريو ولا يساوي تنفيذًا مؤكدًا؛ التنفيذ يبقى مرتبطًا بـ Trigger وStop/Cancel وTarget صالح وبوابات القواعد.';
      grid.insertAdjacentElement('afterend', note);
    }
  };

  const apply = () => {
    decorateDecision();
    decorateSummaryCards();
    ensureLogicStrip();
    decorateReadiness();
  };

  const boot = () => {
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    [250, 700, 1400, 2600].forEach((ms) => setTimeout(apply, ms));
    setTimeout(() => observer.disconnect(), 7000);
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();

// SALEEM_V81_COMPACT_TEXT_CHART_TOOLBAR
(() => {
  const q = (s, root = document) => root.querySelector(s);
  const qa = (s, root = document) => [...root.querySelectorAll(s)];

  // The user explicitly requested deleting only the "ملخص سبب النتيجة" box.
  const removeRejectedSummary = () => {
    qa('.v81p-logic-strip').forEach((el) => el.remove());
  };

  const ensureChartToolbar = () => {
    const tools = q('.v81r-chart-tools');
    if (!tools) return;

    const full = qa('button,a', tools).find((el) => (el.textContent || '').includes('عرض كامل'));
    if (full) {
      full.classList.add('v81c-fullscreen-action');
      if (!full.getAttribute('aria-label')) full.setAttribute('aria-label', 'عرض الشارت كامل');
    }

    let note = q('.v81c-chart-refresh-note', tools);
    if (!note) {
      note = document.createElement('span');
      note.className = 'v81c-chart-refresh-note';
      note.innerHTML = '<strong>↻ تحديث الشارت</strong> — يظهر آخر شارت مع نتيجة التحليل الحالية';
      tools.appendChild(note);
    }
  };

  const apply = () => {
    removeRejectedSummary();
    ensureChartToolbar();
  };

  const boot = () => {
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    [180, 450, 900, 1600, 2800, 4500].forEach((ms) => setTimeout(apply, ms));
    setTimeout(() => observer.disconnect(), 8000);
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();

