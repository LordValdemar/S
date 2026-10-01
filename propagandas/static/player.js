"use strict";

const tela = document.getElementById("tela");
const aviso = document.getElementById("aviso");
const letreiro = document.getElementById("letreiro");

let itens = [];        // última lista recebida (usada se o servidor cair)
let posicao = -1;
let textoLetreiro = null;
let temporizador = null;
let rodada = 0;        // evita que duas trocas aconteçam ao mesmo tempo

// Busca a lista atualizada antes de cada propaganda. Assim, mudanças
// feitas no painel aparecem sem precisar recarregar a tela.
async function atualizarLista() {
  try {
    const resposta = await fetch(document.body.dataset.api, { cache: "no-store" });
    if (!resposta.ok) throw new Error("HTTP " + resposta.status);
    const dados = await resposta.json();
    itens = dados.itens;
    mostrarLetreiro(dados.letreiro);
    return true;
  } catch (erro) {
    console.warn("Sem conexão com o servidor, usando a lista anterior.", erro);
    return false;
  }
}

// Telas que ficam ligadas por semanas: recarrega a página uma vez por dia
// (só quando o servidor responde) para receber atualizações e liberar memória.
const INICIO = Date.now();
const UM_DIA = 24 * 60 * 60 * 1000;

function mostrarLetreiro(texto) {
  if (texto === textoLetreiro) return;
  textoLetreiro = texto;
  const span = letreiro.querySelector("span");
  span.textContent = texto;
  letreiro.style.display = texto ? "block" : "none";
  // Velocidade constante, independente do tamanho do texto.
  span.style.animationDuration = Math.max(10, texto.length * 0.25) + "s";
}

async function proxima() {
  clearTimeout(temporizador);
  const minha = ++rodada;
  const seguir = () => { if (minha === rodada) proxima(); };
  const conectado = await atualizarLista();
  if (minha !== rodada) return;
  if (conectado && Date.now() - INICIO > UM_DIA) {
    location.reload();
    return;
  }

  if (itens.length === 0) {
    tela.innerHTML = "";
    aviso.textContent = "Nenhuma propaganda no ar. Cadastre pelo painel.";
    aviso.style.display = "flex";
    temporizador = setTimeout(seguir, 10000);
    return;
  }
  aviso.style.display = "none";

  posicao = (posicao + 1) % itens.length;
  const item = itens[posicao];

  tela.style.opacity = 0;
  await new Promise(r => setTimeout(r, 600));
  if (minha !== rodada) return;
  tela.innerHTML = "";

  if (item.tipo === "video") {
    const video = document.createElement("video");
    video.src = item.url;
    video.autoplay = true;
    video.playsInline = true;
    video.onended = seguir;
    video.onerror = seguir;
    tela.appendChild(video);
    // Tenta tocar com som; se o navegador bloquear, toca sem som.
    video.play().catch(() => { video.muted = true; video.play().catch(seguir); });
    // Segurança: se o vídeo travar, pula após 10 minutos.
    temporizador = setTimeout(seguir, 10 * 60 * 1000);
  } else {
    const img = document.createElement("img");
    img.src = item.url;
    img.onerror = seguir;
    tela.appendChild(img);
    temporizador = setTimeout(seguir, item.duracao * 1000);
  }
  tela.style.opacity = 1;
}

// Clique ou tecla F para tela cheia.
function telaCheia() {
  if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {});
}
document.addEventListener("click", telaCheia);
document.addEventListener("keydown", e => { if (e.key === "f" || e.key === "F") telaCheia(); });

proxima();
