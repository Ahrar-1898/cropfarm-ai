(() => {
    const navigation = document.getElementById("welcomeNav");
    const toggle = document.getElementById("homeMenuToggle");
    if (!navigation || !toggle) {
        return;
    }

    const closeNavigation = () => {
        navigation.dataset.open = "false";
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Open navigation");
    };

    toggle.addEventListener("click", () => {
        const isOpen = navigation.dataset.open === "true";
        navigation.dataset.open = String(!isOpen);
        toggle.setAttribute("aria-expanded", String(!isOpen));
        toggle.setAttribute("aria-label", isOpen ? "Open navigation" : "Close navigation");
    });

    navigation.querySelectorAll('a[href^="#"]').forEach((link) => {
        link.addEventListener("click", closeNavigation);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeNavigation();
        }
    });

    if ("IntersectionObserver" in window) {
        const links = [...navigation.querySelectorAll("[data-home-nav]")];
        const sections = links
            .map((link) => document.querySelector(link.getAttribute("href")))
            .filter(Boolean);
        const observer = new IntersectionObserver((entries) => {
            const visible = entries
                .filter((entry) => entry.isIntersecting)
                .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
            if (!visible) {
                return;
            }
            links.forEach((link) => {
                if (link.getAttribute("href") === `#${visible.target.id}`) {
                    link.setAttribute("aria-current", "location");
                } else {
                    link.removeAttribute("aria-current");
                }
            });
        }, { rootMargin: "-25% 0px -65% 0px", threshold: [0, 0.1, 0.35] });
        sections.forEach((section) => observer.observe(section));
    }
})();
