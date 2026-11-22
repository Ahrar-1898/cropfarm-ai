(() => {
    const cropInput = document.getElementById("cropImage");
    const cameraInput = document.getElementById("cameraCaptureInput");
    const preview = document.getElementById("imagePreview");
    const uploadPlaceholder = document.getElementById("uploadPlaceholder");
    const uploadStatus = document.getElementById("imageUploadStatus");
    const removeButton = document.getElementById("removeImage");
    const dropZone = document.getElementById("dropZone");
    const form = document.getElementById("scannerForm");
    const galleryButton = document.getElementById("galleryButton");
    const cameraButton = document.getElementById("cameraButton");
    const errorMessage = document.getElementById("scannerError");
    const cameraDialog = document.getElementById("cameraDialog");
    const video = document.getElementById("cameraVideo");
    const canvas = document.getElementById("cameraCanvas");
    const capturePreview = document.getElementById("cameraCapturePreview");
    const captureButton = document.getElementById("capturePhotoButton");
    const retakeButton = document.getElementById("retakePhotoButton");
    const useButton = document.getElementById("usePhotoButton");
    const closeButton = document.getElementById("cameraCloseButton");
    const analyzeLabel = document.getElementById("analyzeLabel");
    const analyzeButton = document.getElementById("analyzeButton");
    const analyzeSpinner = document.getElementById("analyzeSpinner");
    const loadingStatus = document.getElementById("scannerLoading");
    if (!cropInput || !form) {
        return;
    }

    let cameraStream = null;
    let previewUrl = null;
    let capturePreviewUrl = null;
    let capturedFile = null;
    let isSubmitting = false;

    const clearError = () => {
        errorMessage.textContent = "";
        errorMessage.hidden = true;
    };
    const showError = (message) => {
        errorMessage.textContent = message;
        errorMessage.hidden = false;
    };
    const releasePreviewUrl = () => {
        if (previewUrl) {
            URL.revokeObjectURL(previewUrl);
            previewUrl = null;
        }
        if (capturePreviewUrl) {
            URL.revokeObjectURL(capturePreviewUrl);
            capturePreviewUrl = null;
        }
    };
    const clearSelection = () => {
        cropInput.value = "";
        if (cameraInput) {
            cameraInput.value = "";
        }
        releasePreviewUrl();
        preview.hidden = true;
        preview.removeAttribute("src");
        uploadPlaceholder.hidden = false;
        uploadStatus.hidden = true;
        removeButton.hidden = true;
        dropZone.classList.remove("drop-zone-has-image");
        capturedFile = null;
    };
    const stopCamera = () => {
        cameraStream?.getTracks().forEach((track) => track.stop());
        cameraStream = null;
        video.srcObject = null;
    };
    const closeCamera = () => {
        stopCamera();
        if (cameraDialog.open) {
            cameraDialog.close();
        }
        video.hidden = false;
        capturePreview.hidden = true;
        capturePreview.removeAttribute("src");
        if (capturePreviewUrl) {
            URL.revokeObjectURL(capturePreviewUrl);
            capturePreviewUrl = null;
        }
        captureButton.hidden = false;
        retakeButton.hidden = true;
        useButton.hidden = true;
        capturedFile = null;
    };
    const showFile = (file) => {
        if (!file) {
            return false;
        }
        const validType = ["image/jpeg", "image/png", "image/webp"].includes(file.type.toLowerCase());
        const validExtension = /\.(jpe?g|png|webp)$/i.test(file.name);
        if ((!validType && !validExtension) || !file.size || file.size > 10 * 1024 * 1024) {
            clearSelection();
            showError(form.dataset.fileError);
            return false;
        }

        clearError();
        releasePreviewUrl();
        previewUrl = URL.createObjectURL(file);
        preview.src = previewUrl;
        preview.hidden = false;
        uploadPlaceholder.hidden = true;
        uploadStatus.hidden = false;
        removeButton.hidden = false;
        dropZone.classList.add("drop-zone-has-image");
        return true;
    };
    const openFallbackCamera = () => {
        if (cameraInput) {
            cameraInput.click();
        } else {
            showError(form.dataset.cameraUnavailable);
        }
    };
    const setCapturedFile = (file) => {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        cropInput.files = transfer.files;
        showFile(file);
    };

    galleryButton?.addEventListener("click", () => cropInput.click());
    cropInput.addEventListener("change", () => showFile(cropInput.files[0]));
    cameraInput?.addEventListener("change", () => {
        if (cameraInput.files.length && showFile(cameraInput.files[0])) {
            const transfer = new DataTransfer();
            transfer.items.add(cameraInput.files[0]);
            cropInput.files = transfer.files;
        }
    });
    removeButton?.addEventListener("click", () => {
        clearSelection();
        clearError();
    });

    dropZone?.addEventListener("dragover", (event) => {
        event.preventDefault();
        dropZone.classList.add("drop-zone-active");
    });
    dropZone?.addEventListener("dragleave", () => {
        dropZone.classList.remove("drop-zone-active");
    });
    dropZone?.addEventListener("drop", (event) => {
        event.preventDefault();
        dropZone.classList.remove("drop-zone-active");
        if (event.dataTransfer.files.length) {
            cropInput.files = event.dataTransfer.files;
            showFile(cropInput.files[0]);
        }
    });

    cameraButton?.addEventListener("click", async () => {
        clearError();
        video.hidden = false;
        capturePreview.hidden = true;
        capturePreview.removeAttribute("src");
        if (capturePreviewUrl) {
            URL.revokeObjectURL(capturePreviewUrl);
            capturePreviewUrl = null;
        }
        captureButton.hidden = false;
        retakeButton.hidden = true;
        useButton.hidden = true;
        capturedFile = null;
        if (!navigator.mediaDevices?.getUserMedia || !cameraDialog?.showModal) {
            openFallbackCamera();
            return;
        }
        try {
            cameraStream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: { facingMode: { ideal: "environment" } },
            });
            video.srcObject = cameraStream;
            await video.play();
            cameraDialog.showModal();
        } catch (error) {
            stopCamera();
            const message = error.name === "NotAllowedError" || error.name === "SecurityError"
                ? form.dataset.cameraPermission
                : error.name === "NotFoundError" || error.name === "NotReadableError"
                    ? form.dataset.cameraUnavailable
                    : form.dataset.cameraError;
            showError(message);
        }
    });

    captureButton?.addEventListener("click", async () => {
        if (!video.videoWidth || !video.videoHeight) {
            showError(form.dataset.cameraCaptureError);
            return;
        }
        const scale = Math.min(1, 3000 / Math.max(video.videoWidth, video.videoHeight));
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        const context = canvas.getContext("2d");
        if (!context) {
            showError(form.dataset.cameraCaptureError);
            return;
        }
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const imageBlob = await new Promise((resolve) => {
            canvas.toBlob(resolve, "image/jpeg", 0.86);
        });
        if (!imageBlob) {
            showError(form.dataset.cameraCaptureError);
            return;
        }
        capturedFile = new File([imageBlob], `crop-photo-${Date.now()}.jpg`, {
            type: "image/jpeg",
        });
        capturePreviewUrl = URL.createObjectURL(imageBlob);
        capturePreview.src = capturePreviewUrl;
        capturePreview.hidden = false;
        video.hidden = true;
        captureButton.hidden = true;
        retakeButton.hidden = false;
        useButton.hidden = false;
        clearError();
    });

    retakeButton?.addEventListener("click", () => {
        capturePreview.hidden = true;
        capturePreview.removeAttribute("src");
        if (capturePreviewUrl) {
            URL.revokeObjectURL(capturePreviewUrl);
            capturePreviewUrl = null;
        }
        video.hidden = false;
        captureButton.hidden = false;
        retakeButton.hidden = true;
        useButton.hidden = true;
        capturedFile = null;
    });
    useButton?.addEventListener("click", () => {
        if (capturedFile) {
            setCapturedFile(capturedFile);
            closeCamera();
        }
    });
    closeButton?.addEventListener("click", closeCamera);
    cameraDialog?.addEventListener("close", stopCamera);
    cameraDialog?.addEventListener("click", (event) => {
        if (event.target === cameraDialog) {
            closeCamera();
        }
    });
    cameraDialog?.addEventListener("cancel", stopCamera);

    form.addEventListener("submit", (event) => {
        if (isSubmitting) {
            event.preventDefault();
            return;
        }
        if (!cropInput.files.length) {
            event.preventDefault();
            showError(form.dataset.imageRequired);
            galleryButton?.focus();
            return;
        }
        isSubmitting = true;
        clearError();
        analyzeButton.disabled = true;
        galleryButton.disabled = true;
        cameraButton.disabled = true;
        form.setAttribute("aria-busy", "true");
        loadingStatus.hidden = false;
        analyzeSpinner.hidden = false;
        analyzeLabel.textContent = form.dataset.analyzingLabel;
    });
    const analysisResult = document.getElementById("analysisResult");
    if (analysisResult) {
        const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth";
        analysisResult.scrollIntoView({ behavior, block: "start" });
        analysisResult.focus({ preventScroll: true });
    }
    window.addEventListener("pagehide", () => {
        stopCamera();
        releasePreviewUrl();
    });
})();
