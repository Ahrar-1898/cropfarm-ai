document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    const input = button.closest(".auth-password-field")?.querySelector("input");
    if (!input) {
        return;
    }

    button.addEventListener("click", () => {
        const showPassword = input.type === "password";
        input.type = showPassword ? "text" : "password";
        button.textContent = showPassword
            ? button.dataset.hideLabel
            : button.dataset.showLabel;
        button.setAttribute("aria-label", button.textContent);
        button.setAttribute("aria-pressed", String(showPassword));
    });
});
