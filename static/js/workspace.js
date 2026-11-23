(() => {
    const dashboardGreeting = document.getElementById("dashboardGreeting");
    if (dashboardGreeting) {
        const updateGreeting = () => {
            const hour = new Date().getHours();
            const period = hour >= 5 && hour < 12
                ? "morning"
                : hour < 17 && hour >= 12
                    ? "afternoon"
                    : hour < 21 && hour >= 17
                        ? "evening"
                        : "night";
            const greeting = dashboardGreeting.dataset[period];
            const name = dashboardGreeting.dataset.name?.trim();
            if (name) {
                const punctuation = greeting.endsWith("!") ? "!" : "";
                const baseGreeting = punctuation ? greeting.slice(0, -1) : greeting;
                dashboardGreeting.textContent = `${baseGreeting}, ${name}${punctuation}`;
            } else {
                dashboardGreeting.textContent = greeting;
            }
        };

        updateGreeting();
        window.setInterval(updateGreeting, 30_000);
        window.addEventListener("focus", updateGreeting);
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) {
                updateGreeting();
            }
        });
    }

    const sidebar = document.getElementById("workspaceSidebar");
    const menuToggle = document.getElementById("menuToggle");
    const closeSidebar = () => {
        sidebar?.classList.remove("sidebar-open");
        menuToggle?.setAttribute("aria-expanded", "false");
    };

    menuToggle?.addEventListener("click", () => {
        const isOpen = sidebar.classList.toggle("sidebar-open");
        menuToggle.setAttribute("aria-expanded", String(isOpen));
    });

    sidebar?.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", closeSidebar);
    });

    const profileToggle = document.getElementById("profileMenuToggle");
    const profileMenu = document.getElementById("profileMenu");
    const setProfileMenuOpen = (open) => {
        if (!profileToggle || !profileMenu) {
            return;
        }
        profileMenu.hidden = !open;
        profileToggle.setAttribute("aria-expanded", String(open));
        if (open) {
            profileMenu.querySelector("a, button")?.focus();
        }
    };

    profileToggle?.addEventListener("click", () => {
        setProfileMenuOpen(profileMenu.hidden);
    });
    profileToggle?.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown" && profileMenu?.hidden) {
            event.preventDefault();
            setProfileMenuOpen(true);
        }
    });
    profileMenu?.addEventListener("keydown", (event) => {
        const items = [...profileMenu.querySelectorAll('[role="menuitem"]')];
        const currentIndex = items.indexOf(document.activeElement);
        let nextIndex;
        if (event.key === "ArrowDown") {
            nextIndex = (currentIndex + 1) % items.length;
        } else if (event.key === "ArrowUp") {
            nextIndex = (currentIndex - 1 + items.length) % items.length;
        } else if (event.key === "Home") {
            nextIndex = 0;
        } else if (event.key === "End") {
            nextIndex = items.length - 1;
        }
        if (nextIndex !== undefined && items.length) {
            event.preventDefault();
            items[nextIndex].focus();
        }
    });
    document.addEventListener("pointerdown", (event) => {
        if (profileMenu && !profileMenu.hidden
            && !profileMenu.contains(event.target)
            && !profileToggle?.contains(event.target)) {
            setProfileMenuOpen(false);
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && profileMenu && !profileMenu.hidden) {
            setProfileMenuOpen(false);
            profileToggle?.focus();
        }
    });

    document.querySelectorAll("[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });

    const themeButton = document.getElementById("themeToggle");
    const themeStatus = document.getElementById("themeSaveStatus");
    if (!themeButton) {
        return;
    }

    const root = document.documentElement;
    const updateThemeControl = (theme) => {
        const nightMode = theme === "night";
        const label = nightMode
            ? themeButton.dataset.switchToDay
            : themeButton.dataset.switchToNight;
        themeButton.setAttribute("aria-pressed", String(nightMode));
        themeButton.setAttribute("aria-label", label);
        themeButton.title = label;
    };
    const applyTheme = (theme) => {
        root.dataset.theme = theme;
        updateThemeControl(theme);
    };

    const initialTheme = root.dataset.theme === "night" ? "night" : "day";
    applyTheme(initialTheme);

    themeButton.addEventListener("click", async () => {
        const previousTheme = root.dataset.theme === "night" ? "night" : "day";
        const nextTheme = previousTheme === "day" ? "night" : "day";
        themeButton.disabled = true;
        if (themeStatus) {
            themeStatus.textContent = "";
        }
        applyTheme(nextTheme);

        try {
            const response = await fetch(themeButton.dataset.themeUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRFToken": themeButton.dataset.csrfToken,
                },
                body: new URLSearchParams({ theme: nextTheme }),
            });
            const result = await response.json();
            if (!response.ok || !result.saved || result.theme !== nextTheme) {
                throw new Error(result.error || themeButton.dataset.saveError);
            }
        } catch (error) {
            applyTheme(previousTheme);
            if (themeStatus) {
                themeStatus.textContent = themeButton.dataset.saveError;
            }
            console.error("Could not save the selected theme.", error);
        } finally {
            themeButton.disabled = false;
        }
    });
})();
