// Pede confirmação antes de enviar formulários marcados com data-confirmar.
document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
  form.addEventListener("submit", function (evento) {
    if (!confirm(form.dataset.confirmar)) evento.preventDefault();
  });
});
