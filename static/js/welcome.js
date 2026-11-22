(() => {
    const config = window.CropFarmAIAnimationConfig;
    const main = document.querySelector(".welcome-main");
    const video = document.getElementById("welcomeBackgroundVideo");
    const embed = document.getElementById("welcomeEmbed");
    const fallbackImage = document.querySelector(".welcome-background-image");
    const mediaStatus = document.getElementById("welcomeBackgroundStatus");
    const soundToggle = document.getElementById("welcomeSoundToggle");
    const dialog = document.getElementById("languageDialog");
    const languageForm = document.getElementById("languagePreferenceForm");
    const languageSearch = document.getElementById("languageSearch");
    const languageButtons = [...document.querySelectorAll(".language-option")];
    const selectedLanguage = document.getElementById("selectedLanguage");
    const continueButton = document.getElementById("continueWithLanguage");
    const skipButton = document.getElementById("skipLanguage");
    const feedback = document.getElementById("languageDialogFeedback");
    const globalFeedback = document.getElementById("languageGlobalFeedback");
    const coverage = document.getElementById("languageCoverage");
    const openLanguageDialog = document.getElementById("openLanguageDialog");
    const closeLanguageDialog = document.getElementById("closeLanguageDialog");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    if (!main || !dialog || !languageForm) {
        return;
    }

    const setMediaStatus = (message) => {
        if (mediaStatus) {
            mediaStatus.textContent = message;
        }
    };

    const safeFallbackImage = () => {
        if (!config || !config.fallbackImage || !fallbackImage) {
            return;
        }
        try {
            const url = new URL(config.fallbackImage, window.location.origin);
            if (
                url.origin === window.location.origin ||
                (url.protocol === "https:" && url.hostname === "images.unsplash.com")
            ) {
                fallbackImage.src = url.href;
            }
        } catch (error) {
            setMediaStatus(mediaStatus.dataset.messageUnavailable);
            console.error("Invalid welcome fallback image URL.", error);
        }
    };

    const videoSources = () => {
        const mobile = window.matchMedia("(max-width: 700px)").matches;
        const configured = mobile && config.mobileSources.length
            ? config.mobileSources
            : config.desktopSources;
        return configured.map((source) => {
            const url = new URL(source.url, window.location.origin);
            if (
                url.origin !== window.location.origin ||
                !url.pathname.startsWith("/static/animations/") ||
                !["video/mp4", "video/webm"].includes(source.type)
            ) {
                throw new Error("Local background videos must be MP4 or WebM files in static/animations.");
            }
            return { url: url.href, type: source.type };
        });
    };

    const directVideoSource = () => {
        const url = new URL(config.directVideoUrl);
        if (
            url.protocol !== "https:" ||
            !["video/mp4", "video/webm"].includes(config.directMimeType)
        ) {
            throw new Error("Direct background videos require an HTTPS MP4 or WebM URL.");
        }
        return { url: url.href, type: config.directMimeType };
    };

    const embedUrl = () => {
        const url = new URL(config.embedUrl);
        if (url.protocol !== "https:") {
            throw new Error("Background video embeds must use HTTPS.");
        }

        const host = url.hostname.toLowerCase();
        if (host === "youtu.be" || host === "www.youtube.com" || host === "youtube.com") {
            const id = host === "youtu.be"
                ? url.pathname.split("/").filter(Boolean)[0]
                : url.pathname === "/watch"
                    ? url.searchParams.get("v")
                    : url.pathname.match(/^\/(?:embed|shorts)\/([A-Za-z0-9_-]{11})$/)?.[1];
            if (!id || !/^[A-Za-z0-9_-]{11}$/.test(id)) {
                throw new Error("The YouTube URL does not contain a valid video ID.");
            }
            const player = new URL(`https://www.youtube-nocookie.com/embed/${id}`);
            player.searchParams.set("autoplay", "1");
            player.searchParams.set("mute", "1");
            player.searchParams.set("loop", "1");
            player.searchParams.set("playlist", id);
            player.searchParams.set("controls", "0");
            player.searchParams.set("playsinline", "1");
            return player.href;
        }

        if (host === "vimeo.com" || host === "www.vimeo.com") {
            const id = url.pathname.split("/").filter(Boolean).at(-1);
            if (!id || !/^\d+$/.test(id)) {
                throw new Error("The Vimeo URL does not contain a valid video ID.");
            }
            const player = new URL(`https://player.vimeo.com/video/${id}`);
            player.searchParams.set("autoplay", "1");
            player.searchParams.set("muted", "1");
            player.searchParams.set("loop", "1");
            player.searchParams.set("background", "1");
            return player.href;
        }
        throw new Error("Use a supported YouTube or Vimeo URL for an embedded background.");
    };

    const showFallback = (message) => {
        if (video) {
            video.pause();
            video.hidden = true;
            video.removeAttribute("src");
            video.replaceChildren();
        }
        if (embed) {
            embed.replaceChildren();
        }
        if (soundToggle) {
            soundToggle.hidden = true;
        }
        setMediaStatus(message);
    };

    const startConfiguredVideo = (sources) => {
        if (!video || !sources.length) {
            throw new Error("No background video sources are configured.");
        }
        for (const source of sources) {
            const element = document.createElement("source");
            element.src = source.url;
            element.type = source.type;
            video.append(element);
        }
        video.loop = Boolean(config.loop);
        video.muted = Boolean(config.muted);
        video.playsInline = Boolean(config.playsInline);
        video.preload = ["none", "metadata", "auto"].includes(config.preload)
            ? config.preload
            : "metadata";
        const rate = Number(config.playbackRate);
        video.playbackRate = Number.isFinite(rate) && rate >= 0.25 && rate <= 2 ? rate : 1;
        video.hidden = false;
        video.addEventListener("error", () => {
            showFallback(mediaStatus.dataset.messageUnavailable);
        }, { once: true });

        video.addEventListener("loadedmetadata", () => {
            const positionKey = `${main.dataset.languageOnboardingKey}:video-position`;
            try {
                const savedPosition = Number(window.sessionStorage.getItem(positionKey));
                if (Number.isFinite(savedPosition) && savedPosition > 0 && savedPosition < video.duration) {
                    video.currentTime = savedPosition;
                }
                window.sessionStorage.removeItem(positionKey);
            } catch (error) {
                console.warn("Could not restore the welcome video position.", error);
            }
            if (config.autoplay && !reducedMotion.matches) {
                video.play().then(() => {
                    setMediaStatus("");
                    if (soundToggle) {
                        soundToggle.hidden = false;
                        soundToggle.setAttribute("aria-pressed", String(!video.muted));
                        soundToggle.setAttribute(
                            "aria-label",
                            video.muted
                                ? soundToggle.dataset.labelSoundOn
                                : soundToggle.dataset.labelSoundOff,
                        );
                    }
                }).catch((error) => {
                    showFallback(mediaStatus.dataset.messageUnavailable);
                    console.warn("The welcome background video could not autoplay.", error);
                });
            }
        }, { once: true });
        video.load();
    };

    const startConfiguredEmbed = (url) => {
        if (!embed) {
            throw new Error("The background video embed container is missing.");
        }
        const iframe = document.createElement("iframe");
        iframe.src = url;
        iframe.title = "CropFarmAI welcome background video";
        iframe.allow = "autoplay; fullscreen; picture-in-picture";
        iframe.referrerPolicy = "strict-origin-when-cross-origin";
        iframe.loading = "eager";
        embed.replaceChildren(iframe);
        setMediaStatus("");
    };

    const configureBackground = () => {
        safeFallbackImage();
        if (!config || !config.enabled || reducedMotion.matches) {
            const message = reducedMotion.matches
                ? ""
                : mediaStatus.dataset.messageUnconfigured;
            showFallback(message);
            return;
        }

        try {
            if (config.sourceType === "local") {
                startConfiguredVideo(videoSources());
            } else if (config.sourceType === "direct") {
                startConfiguredVideo([directVideoSource()]);
            } else if (config.sourceType === "embed") {
                startConfiguredEmbed(embedUrl());
            } else {
                throw new Error("Unsupported welcome animation source type.");
            }
        } catch (error) {
            showFallback(mediaStatus.dataset.messageUnavailable);
            console.error("Welcome background animation configuration is invalid.", error);
        }
    };

    const updateCoverage = (status) => {
        const messageKey = status === "complete"
            ? "coverageComplete"
            : status === "partial"
                ? "coveragePartial"
                : "coverageFallback";
        coverage.textContent = dialog.dataset[messageKey];
    };

    const chooseLanguage = (button) => {
        languageButtons.forEach((option) => {
            option.setAttribute("aria-selected", String(option === button));
        });
        selectedLanguage.value = button.dataset.languageCode;
        continueButton.disabled = false;
        updateCoverage(button.dataset.translationStatus);
    };

    const openDialog = () => {
        feedback.textContent = "";
        if (!dialog.open) {
            dialog.showModal();
        }
        languageSearch.focus();
    };

    const savePreference = async (language) => {
        feedback.textContent = "";
        const formData = new FormData(languageForm);
        formData.set("language", language);
        try {
            const response = await fetch(languageForm.action, {
                method: "POST",
                body: formData,
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) {
                throw new Error(`Language preference request failed (${response.status}).`);
            }
            const result = await response.json();
            if (result.saved !== true || result.language !== language) {
                throw new Error("The language preference was not confirmed by the server.");
            }
            return true;
        } catch (error) {
            feedback.textContent = dialog.dataset.saveError;
            globalFeedback.textContent = dialog.dataset.saveError;
            console.error("Could not save the selected language.", error);
            return false;
        }
    };

    const saveVideoPosition = () => {
        if (!video || video.hidden || !Number.isFinite(video.currentTime)) {
            return;
        }
        try {
            window.sessionStorage.setItem(
                `${main.dataset.languageOnboardingKey}:video-position`,
                String(video.currentTime),
            );
        } catch (error) {
            console.warn("Could not preserve the welcome video position.", error);
        }
    };

    const completeLanguageSelection = async (language) => {
        const saved = await savePreference(language);
        if (!saved) {
            return false;
        }
        saveVideoPosition();
        window.location.reload();
        return true;
    };

    const dismissLanguagePrompt = async () => {
        const saved = await savePreference(main.dataset.language);
        if (!saved) {
            dialog.close();
            return;
        }
        dialog.close();
    };

    languageButtons.forEach((button) => {
        button.addEventListener("click", () => chooseLanguage(button));
    });

    languageSearch.addEventListener("input", () => {
        const query = languageSearch.value.trim().toLocaleLowerCase();
        languageButtons.forEach((button) => {
            button.hidden = !button.dataset.languageName.includes(query);
        });
    });

    languageForm.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!selectedLanguage.value || continueButton.disabled) {
            return;
        }
        void completeLanguageSelection(selectedLanguage.value);
    });

    skipButton.addEventListener("click", () => {
        void completeLanguageSelection("en");
    });

    closeLanguageDialog.addEventListener("click", () => {
        void dismissLanguagePrompt();
    });

    dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        void dismissLanguagePrompt();
    });

    openLanguageDialog.addEventListener("click", openDialog);

    if (soundToggle) {
        soundToggle.addEventListener("click", () => {
            if (!video || video.hidden) {
                return;
            }
            video.muted = !video.muted;
            soundToggle.setAttribute("aria-pressed", String(!video.muted));
            soundToggle.setAttribute(
                "aria-label",
                video.muted
                    ? soundToggle.dataset.labelSoundOn
                    : soundToggle.dataset.labelSoundOff,
            );
        });
    }

    const activeLanguage = languageButtons.find(
        (button) => button.dataset.languageCode === main.dataset.language,
    );
    if (activeLanguage) {
        chooseLanguage(activeLanguage);
    }
    configureBackground();

    if (main.dataset.languagePromptDone !== "true") {
        window.setTimeout(openDialog, 10_000);
    }
})();
