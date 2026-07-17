(() => {
  const form = document.getElementById('analysis-form');
  const fileInput = document.getElementById('image-input');
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
    ['dragenter','dragover'].forEach(evt => dropZone.addEventListener(evt, e => {
      e.preventDefault();
      dropZone.classList.add('dragging');
    }));
    ['dragleave','drop'].forEach(evt => dropZone.addEventListener(evt, e => {
      e.preventDefault();
      dropZone.classList.remove('dragging');
    }));
    dropZone.addEventListener('drop', e => {
      const files = e.dataTransfer?.files;
      if (files?.length) {
        const dt = new DataTransfer();
        dt.items.add(files[0]);
        fileInput.files = dt.files;
        fileName.textContent = files[0].name;
      }
    });
  }

  if (form) form.addEventListener('submit', e => {
    if (!fileInput?.files?.length) {
      e.preventDefault();
      dropZone?.animate(
        [{transform:'translateX(0)'},{transform:'translateX(-6px)'},{transform:'translateX(6px)'},{transform:'translateX(0)'}],
        {duration:340}
      );
      return;
    }

    processingCard.hidden = false;
    processingCard.scrollIntoView({behavior:'smooth',block:'center'});
    let p = 2;
    let currentStep = 0;
    const labels = ['قراءة صورة الشارت','تحليل الاتجاه العام','تحديد الدعم والمقاومة','تحليل السيناريوهات','إنشاء صورة التحليل'];
    const timer = setInterval(() => {
      p = Math.min(94, p + Math.max(1, Math.round((95-p)/17)));
      progressRing.style.setProperty('--progress', p);
      progressValue.textContent = `${p}%`;
      const nextStep = Math.min(4, Math.floor(p/19));
      if (nextStep !== currentStep) {
        currentStep = nextStep;
        steps.forEach((s,i)=>s.classList.toggle('active',i<=currentStep));
        message.textContent = labels[currentStep];
      }
      if (p >= 94) clearInterval(timer);
    }, 240);
  });
})();
