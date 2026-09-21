// Máscara automática de CPF/CNPJ nos campos marcados com data-mascara.
// O usuário digita só números — pontos, barra e hífen entram sozinhos.
(function () {
    function apenasDigitos(valor) {
        return (valor || "").replace(/\D/g, "");
    }

    function formataCpf(digitos) {
        digitos = digitos.slice(0, 11);
        var valor = digitos;
        if (digitos.length > 3) valor = digitos.slice(0, 3) + "." + digitos.slice(3);
        if (digitos.length > 6) valor = digitos.slice(0, 3) + "." + digitos.slice(3, 6) + "." + digitos.slice(6);
        if (digitos.length > 9) valor = digitos.slice(0, 3) + "." + digitos.slice(3, 6) + "." + digitos.slice(6, 9) + "-" + digitos.slice(9);
        return valor;
    }

    function formataCnpj(digitos) {
        digitos = digitos.slice(0, 14);
        var valor = digitos;
        if (digitos.length > 2) valor = digitos.slice(0, 2) + "." + digitos.slice(2);
        if (digitos.length > 5) valor = digitos.slice(0, 2) + "." + digitos.slice(2, 5) + "." + digitos.slice(5);
        if (digitos.length > 8) valor = digitos.slice(0, 2) + "." + digitos.slice(2, 5) + "." + digitos.slice(5, 8) + "/" + digitos.slice(8);
        if (digitos.length > 12) valor = digitos.slice(0, 2) + "." + digitos.slice(2, 5) + "." + digitos.slice(5, 8) + "/" + digitos.slice(8, 12) + "-" + digitos.slice(12);
        return valor;
    }

    // Campo único de Cliente (CPF ou CNPJ): até 11 dígitos vira CPF,
    // a partir do 12º dígito passa a formatar como CNPJ.
    function formataDocumento(digitos) {
        digitos = digitos.slice(0, 14);
        return digitos.length > 11 ? formataCnpj(digitos) : formataCpf(digitos);
    }

    var FORMATADORES = {
        cnpj: { formata: formataCnpj, maxDigitos: 14 },
        documento: { formata: formataDocumento, maxDigitos: 14 },
    };

    function aplicaMascara(campo) {
        var config = FORMATADORES[campo.getAttribute("data-mascara")];
        if (!config) return;

        function atualiza() {
            var cursorAntigo = campo.selectionStart;
            var digitosAntesDoCursor = apenasDigitos(campo.value.slice(0, cursorAntigo)).length;

            var digitos = apenasDigitos(campo.value).slice(0, config.maxDigitos);
            campo.value = config.formata(digitos);

            // Recoloca o cursor depois do mesmo número de dígitos que tinha antes,
            // para o usuário poder editar no meio do valor sem o cursor pular pro fim.
            var pos = 0, digitosContados = 0;
            while (pos < campo.value.length && digitosContados < digitosAntesDoCursor) {
                if (/\d/.test(campo.value[pos])) digitosContados++;
                pos++;
            }
            campo.setSelectionRange(pos, pos);
        }

        campo.addEventListener("input", atualiza);
        if (campo.value) atualiza(); // reformata valor já preenchido (ex.: reabertura do form com erro)
    }

    document.addEventListener("DOMContentLoaded", function () {
        var campos = document.querySelectorAll("[data-mascara]");
        for (var i = 0; i < campos.length; i++) aplicaMascara(campos[i]);
    });
})();
