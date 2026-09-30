(() => {
  "use strict";
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".site-nav");
  if (toggle && nav) {
    const close = () => { toggle.setAttribute("aria-expanded", "false"); nav.classList.remove("is-open"); };
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
    });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") close(); });
    nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", close));
  }

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.parentElement && button.parentElement.querySelector("input");
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-label", show ? "Скрыть пароль" : "Показать пароль");
      button.classList.toggle("is-visible", show);
    });
  });

  const phone = document.querySelector("[data-phone-mask]");
  if (phone) phone.addEventListener("input", () => {
    let digits = phone.value.replace(/\D/g, "").slice(0, 11);
    if (digits && digits[0] !== "8") digits = ("8" + digits).slice(0, 11);
    let value = digits.slice(0, 1);
    if (digits.length > 1) value += "(" + digits.slice(1, 4);
    if (digits.length >= 4) value += ")";
    if (digits.length > 4) value += digits.slice(4, 7);
    if (digits.length > 7) value += "-" + digits.slice(7, 9);
    if (digits.length > 9) value += "-" + digits.slice(9, 11);
    phone.value = value;
  });

  const select = document.querySelector("[data-room-select]");
  const hint = document.querySelector("[data-room-hint]");
  const attendees = document.querySelector("#attendees");
  if (select && hint && attendees) {
    const update = () => {
      const option = select.options[select.selectedIndex];
      const capacity = option && option.dataset.capacity;
      if (capacity) {
        attendees.max = capacity;
        hint.textContent = option.dataset.city + " · вместимость до " + capacity + " чел.";
      } else {
        attendees.removeAttribute("max");
        hint.textContent = "В каталоге доступны три типа площадок";
      }
    };
    select.addEventListener("change", update);
    update();
  }
})();
