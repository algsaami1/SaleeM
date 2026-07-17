(() => {
  const form = document.getElementById('analysis-form');
  const fileInput = document.getElementById('image-input');
  const fileName = document.getElementById('file-name');
  const dropZone = document.getElementById('drop-zone');
  const processingCard = document.getElementById('processing-card');
  const progressRing = document.getElementById('progress-ring');
  const progressValue = document.getElementById('progress-value');
  const steps = processingCard ? [...processingCard.querySelectorAll('.steps span')] : [];

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
})();
