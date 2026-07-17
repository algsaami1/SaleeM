(() => {
  const form = document.getElementById('analysis-form');
  const fileInput = document.getElementById('image-input');
  const urlInput = document.getElementById('image-url');
  const fileName = document.getElementById('file-name');
  const dropZone = document.getElementById('drop-zone');
  const processingCard = document.getElementById('processing-card');
  const progressRing = document.getElementById('progress-ring');
  const progressValue = document.getElementById('progress-value');
  const message = document.getElementById('processing-message');
  const steps = processingCard ? [...processingCard.querySelectorAll('.steps span')] : [];

  if (fileInput) fileInput.addEventListener('change', () => {
    fileName.textContent = fileInput.files?.[0]?.name || 'لم يتم اختيار صورة';
  });

  if (dropZone) {
    ['dragenter','dragover'].forEach(evt => dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.add('dragging'); }));
    ['dragleave','drop'].forEach(evt => dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.remove('dragging'); }));
    dropZone.addEventListener('drop', e => {
      const files = e.dataTransfer?.files;
      if (files?.length) {
        const dt = new DataTransfer(); dt.items.add(files[0]); fileInput.files = dt.files;
        fileName.textContent = files[0].name;
      }
    });
  }

  if (form) form.addEventListener('submit', e => {
    const hasFile = fileInput?.files?.length;
    const hasUrl = urlInput?.value.trim();
    if (!hasFile && !hasUrl) {
      e.preventDefault();
      dropZone?.animate([{transform:'translateX(0)'},{transform:'translateX(-7px)'},{transform:'translateX(7px)'},{transform:'translateX(0)'}],{duration:360});
      return;
    }
    processingCard.hidden = false;
    processingCard.scrollIntoView({behavior:'smooth',block:'center'});
    let p = 2; let currentStep = 0;
    const labels = ['قراءة صورة الشارت','تحليل الاتجاه العام','تحديد الدعم والمقاومة','إنشاء صورة التحليل'];
    const timer = setInterval(() => {
      p = Math.min(94, p + Math.max(1, Math.round((95-p)/16)));
      progressRing.style.setProperty('--progress', p);
      progressValue.textContent = `${p}%`;
      const nextStep = Math.min(3, Math.floor(p/24));
      if (nextStep !== currentStep) {
        currentStep = nextStep;
        steps.forEach((s,i)=>s.classList.toggle('active',i<=currentStep));
        message.textContent = labels[currentStep];
      }
      if (p >= 94) clearInterval(timer);
    }, 240);
  });
})();
