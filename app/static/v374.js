
(() => {
  const ready = (fn) => {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  };

  ready(() => {
    const input = document.getElementById('image-input');
    const form = document.getElementById('analysis-form');
    const dropZone = document.getElementById('drop-zone');
    const preview = document.getElementById('upload-chart-preview');
    const placeholder = document.getElementById('upload-chart-placeholder');
    const changeButton = document.getElementById('upload-chart-change');
    const note = document.getElementById('upload-orientation-note');

    let uploadValid = false;
    let checking = false;
    const MIN_W = 800;
    const MIN_H = 400;
    const MIN_RATIO = 1.15;

    const setNote = (message, tone = '') => {
      if (!note) return;
      note.textContent = message;
      note.classList.remove('good', 'bad');
      if (tone) note.classList.add(tone);
    };

    const inspect = (file) => new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const width = img.naturalWidth || 0;
        const height = img.naturalHeight || 0;
        URL.revokeObjectURL(url);
        resolve({ width, height });
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error('read'));
      };
      img.src = url;
    });

    const clearInvalidPreview = () => {
      if (preview) {
        preview.hidden = true;
        preview.removeAttribute('src');
      }
      if (placeholder) placeholder.hidden = false;
      if (changeButton) changeButton.hidden = true;
      dropZone?.classList.remove('has-preview');
      dropZone?.classList.add('upload-invalid');
    };

    const validateFile = async () => {
      const file = input?.files?.[0];
      uploadValid = false;

      if (!file) {
        checking = false;
        setNote('يشترط صورة أفقية واضحة يظهر فيها الشارت ومحور الأسعار.');
        return false;
      }

      checking = true;
      setNote('جاري التحقق من اتجاه الصورة ووضوحها...');

      try {
        const { width, height } = await inspect(file);
        const ratio = width / Math.max(1, height);

        if (width <= height || ratio < MIN_RATIO) {
          if (input) input.value = '';
          clearInvalidPreview();
          setNote('الصورة رأسية. دوّر الهاتف للوضع الأفقي والتقط الشارت كاملًا ثم أعد الرفع.', 'bad');
          checking = false;
          return false;
        }

        if (width < MIN_W || height < MIN_H) {
          if (input) input.value = '';
          clearInvalidPreview();
          setNote(`الصورة أفقية لكن دقتها منخفضة (${width}×${height}). ارفع صورة أوضح لا تقل تقريبًا عن 800×400.`, 'bad');
          checking = false;
          return false;
        }

        uploadValid = true;
        checking = false;
        dropZone?.classList.remove('upload-invalid');
        setNote(`صورة أفقية مناسبة (${width}×${height}) — جاهزة للتحليل.`, 'good');
        return true;
      } catch {
        if (input) input.value = '';
        clearInvalidPreview();
        checking = false;
        setNote('تعذر قراءة الصورة. اختر لقطة أفقية واضحة جديدة.', 'bad');
        return false;
      }
    };

    input?.addEventListener('change', () => {
      void validateFile();
    }, true);

    form?.addEventListener('submit', (event) => {
      if (checking || !uploadValid) {
        event.preventDefault();
        event.stopImmediatePropagation();
        setNote(
          checking ? 'انتظر لحظة حتى يكتمل فحص الصورة.' : 'اختر صورة أفقية واضحة قبل بدء التحليل.',
          'bad'
        );
        dropZone?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, true);

    document.addEventListener('paste', (event) => {
      if (!input) return;
      const files = Array.from(event.clipboardData?.files || []);
      const image = files.find((file) => String(file.type || '').startsWith('image/'));
      if (!image) return;
      event.preventDefault();
      const dt = new DataTransfer();
      dt.items.add(image);
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      dropZone?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });

    // Gallery-style full screen: separate overlay, never closes on finger release.
    const chart = document.querySelector('.terminal-chart-card');
    const source = document.getElementById('result-image');
    if (!chart || !source) return;

    const oldFocus = chart.querySelector('.chart-focus-toggle-v371');
    if (oldFocus) oldFocus.hidden = true;

    const openButton = document.createElement('button');
    openButton.type = 'button';
    openButton.className = 'gallery-open-button-v374';
    openButton.innerHTML = '<span aria-hidden="true">⛶</span><b>عرض كامل</b>';
    chart.appendChild(openButton);

    const overlay = document.createElement('div');
    overlay.className = 'saleem-gallery-v374';
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="saleem-gallery-stage-v374">
        <img class="saleem-gallery-image-v374" alt="شارت SaleeM بكامل الشاشة" draggable="false">
      </div>
      <button class="saleem-gallery-close-v374" type="button" aria-label="رجوع">×</button>
      <div class="saleem-gallery-toolbar-v374">
        <button type="button" data-a="out">−</button>
        <output class="saleem-gallery-zoom-v374">100%</output>
        <button type="button" data-a="in">＋</button>
        <button type="button" data-a="reset">ملاءمة</button>
      </div>
      <div class="saleem-gallery-hint-v374">اسحب بحرية • قرّب بإصبعين • ضغطتين للتكبير</div>
    `;
    document.body.appendChild(overlay);

    const stage = overlay.querySelector('.saleem-gallery-stage-v374');
    const image = overlay.querySelector('.saleem-gallery-image-v374');
    const close = overlay.querySelector('.saleem-gallery-close-v374');
    const zoomOut = overlay.querySelector('[data-a="out"]');
    const zoomIn = overlay.querySelector('[data-a="in"]');
    const resetButton = overlay.querySelector('[data-a="reset"]');
    const zoomValue = overlay.querySelector('.saleem-gallery-zoom-v374');
    const hint = overlay.querySelector('.saleem-gallery-hint-v374');

    let scale = 1;
    let x = 0;
    let y = 0;
    let mode = '';
    let sx = 0, sy = 0, ox = 0, oy = 0;
    let pDistance = 1, pScale = 1, ax = 0, ay = 0;
    let lastTap = 0, tapX = 0, tapY = 0, moved = false;

    const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

    const panBounds = () => {
      const r = stage.getBoundingClientRect();
      const w = Math.max(1, image.offsetWidth) * scale;
      const h = Math.max(1, image.offsetHeight) * scale;
      return {
        x: Math.max(0, (w - r.width) / 2) + r.width * 0.20,
        y: Math.max(0, (h - r.height) / 2) + r.height * 0.20,
      };
    };

    const keepInReach = () => {
      const b = panBounds();
      x = clamp(x, -b.x, b.x);
      y = clamp(y, -b.y, b.y);
    };

    const render = (animate = false) => {
      image.classList.toggle('animate', animate);
      image.style.transform = `translate(-50%,-50%) translate3d(${x}px,${y}px,0) scale(${scale})`;
      if (zoomValue) zoomValue.textContent = `${Math.round(scale * 100)}%`;
      if (animate) setTimeout(() => image.classList.remove('animate'), 180);
    };

    const reset = (animate = true) => {
      scale = 1;
      x = 0;
      y = 0;
      render(animate);
    };

    const zoom = (next, clientX = null, clientY = null, animate = false) => {
      const old = scale;
      const target = clamp(next, 1, 6);
      if (Math.abs(target - old) < 0.001) return;

      const r = stage.getBoundingClientRect();
      const lx = (clientX ?? (r.left + r.width / 2)) - (r.left + r.width / 2);
      const ly = (clientY ?? (r.top + r.height / 2)) - (r.top + r.height / 2);
      const anchorX = (lx - x) / old;
      const anchorY = (ly - y) / old;

      scale = target;
      x = lx - anchorX * target;
      y = ly - anchorY * target;
      keepInReach();
      render(animate);
      hint?.classList.add('hide');
    };

    const open = () => {
      image.src = source.currentSrc || source.src;
      overlay.hidden = false;
      document.body.classList.add('saleem-gallery-open-v374');
      reset(false);
      requestAnimationFrame(() => hint?.classList.remove('hide'));
    };

    const closeOverlay = () => {
      overlay.hidden = true;
      document.body.classList.remove('saleem-gallery-open-v374');
      mode = '';
    };

    openButton.addEventListener('click', open);
    close.addEventListener('click', closeOverlay);
    zoomIn.addEventListener('click', () => zoom(scale + 0.5, null, null, true));
    zoomOut.addEventListener('click', () => zoom(scale - 0.5, null, null, true));
    resetButton.addEventListener('click', () => reset(true));

    stage.addEventListener('touchstart', (event) => {
      hint?.classList.add('hide');
      moved = false;

      if (event.touches.length >= 2) {
        event.preventDefault();
        mode = 'pinch';
        const a = event.touches[0], b = event.touches[1];
        pDistance = Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY) || 1;
        pScale = scale;
        const r = stage.getBoundingClientRect();
        const mx = (a.clientX + b.clientX) / 2 - (r.left + r.width / 2);
        const my = (a.clientY + b.clientY) / 2 - (r.top + r.height / 2);
        ax = (mx - x) / scale;
        ay = (my - y) / scale;
      } else if (event.touches.length === 1) {
        mode = 'pan';
        sx = tapX = event.touches[0].clientX;
        sy = tapY = event.touches[0].clientY;
        ox = x;
        oy = y;
      }
    }, { passive: false });

    stage.addEventListener('touchmove', (event) => {
      if (event.touches.length >= 2) {
        event.preventDefault();
        moved = true;
        const a = event.touches[0], b = event.touches[1];
        const d = Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY) || 1;
        const r = stage.getBoundingClientRect();
        const mx = (a.clientX + b.clientX) / 2 - (r.left + r.width / 2);
        const my = (a.clientY + b.clientY) / 2 - (r.top + r.height / 2);
        scale = clamp(pScale * (d / pDistance), 1, 6);
        x = mx - ax * scale;
        y = my - ay * scale;
        keepInReach();
        render(false);
      } else if (event.touches.length === 1 && mode === 'pan') {
        event.preventDefault();
        const dx = event.touches[0].clientX - sx;
        const dy = event.touches[0].clientY - sy;
        if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved = true;
        x = ox + dx;
        y = oy + dy;
        keepInReach();
        render(false);
      }
    }, { passive: false });

    stage.addEventListener('touchend', (event) => {
      // Do not close or reset on release.
      keepInReach();
      render(false);

      if (mode === 'pan' && event.changedTouches.length === 1 && !moved) {
        const t = event.changedTouches[0];
        const now = Date.now();
        const distance = Math.hypot(t.clientX - tapX, t.clientY - tapY);
        if (distance < 12 && now - lastTap < 320) {
          if (scale > 1.15) reset(true);
          else zoom(2.5, t.clientX, t.clientY, true);
          lastTap = 0;
        } else if (distance < 12) {
          lastTap = now;
        }
      }

      if (event.touches.length === 1) {
        mode = 'pan';
        sx = event.touches[0].clientX;
        sy = event.touches[0].clientY;
        ox = x;
        oy = y;
      } else if (!event.touches.length) {
        mode = '';
      }
    }, { passive: false });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !overlay.hidden) closeOverlay();
    });
  });
})();
