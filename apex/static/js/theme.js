(() => {
  const control = document.getElementById("apex-theme");
  function apply(value) {
    const theme = ["dark", "light", "system"].includes(value) ? value : "dark";
    document.documentElement.dataset.theme = theme;
    control.value = theme;
  }
  try {
    apply(localStorage.getItem("apex-autolab-theme"));
  } catch {
    apply("dark");
  }
  control.addEventListener("change", () => {
    apply(control.value);
    try {
      localStorage.setItem("apex-autolab-theme", control.value);
    } catch {
      /* Restricted storage: theme still works this session. */
    }
  });
})();
