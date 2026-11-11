// Formulario de entrega (RF-51): el enlace «Abrir Filedoc» solo se muestra cuando el medio elegido es FileDoc.
document.addEventListener('DOMContentLoaded', function(){
  var medio = document.getElementById('id_medio');
  var enlace = document.getElementById('enlace-filedoc');
  if (!medio || !enlace) return;
  function mostrar(){ enlace.hidden = medio.value !== 'FILEDOC'; }
  medio.addEventListener('change', mostrar);
  mostrar();
});
