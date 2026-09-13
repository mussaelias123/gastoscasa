/*
================================================================================
ARCHIVO: static/resumen.js
================================================================================
El dashboard analitico: KPIs, navegador de mes y los graficos de Chart.js.

SE CARGA EN DOS PAGINAS: /resumen (el fondo familiar) y /personal (la cuenta
propia de cada uno). Lo unico que cambia entre las dos son los datos, que la
pagina inyecta ANTES de este script:

    var MOVIMIENTOS  = [...]   // los movimientos a analizar
    var GASTOS_FIJOS = [...]   // vacio en /personal: los fijos son del fondo

Vivia inline dentro de resumen.html. Se saco tal cual —sin un solo cambio de
logica— cuando /personal necesito el mismo dashboard: la alternativa era
duplicar 530 lineas de graficos.

El markup que rellena esta en templates/_dashboard_resumen.html, que tambien
comparten las dos paginas.
================================================================================
*/

(function () {
  if (!MOVIMIENTOS.length) return;

  /* ── CSS variables ──────────────────────────────────────────────────────── */
  var cs = getComputedStyle(document.documentElement);
  function cv(n) { return cs.getPropertyValue(n).trim(); }

  var C = {
    exito:    cv('--color-exito'),
    peligro:  cv('--color-peligro'),
    acento:   cv('--color-acento'),
    acentoOsc:cv('--color-acento-oscuro'),
    elias:    cv('--color-persona-elias'),
    mari:     cv('--color-persona-mari'),
    borde:    cv('--color-borde'),
    textoS:   cv('--color-texto-muted'),
    ars:      cv('--color-moneda-ars'),
    usd:      cv('--color-moneda-usd'),
    alerta:   cv('--color-alerta'),
    superficie: cv('--color-superficie'),
    deco2:    cv('--color-deco-2'),
    deco3:    cv('--color-deco-3'),
    deco4:    cv('--color-deco-4'),
  };

  var PALETA = [C.acento, C.elias, C.mari, C.exito, C.alerta, C.peligro,
                C.ars, C.usd, C.acentoOsc, C.deco2, C.deco3];

  /* ── Formatters (todo en USD) ──────────────────────────────────────────── */
  function fmtUSD(v) {
    var s = v < 0 ? '-' : '';
    var n = new Intl.NumberFormat('de-DE', {minimumFractionDigits:2, maximumFractionDigits:2}).format(Math.abs(v));
    return 'USD ' + s + n;
  }
  function fmtCorto(v) {
    var abs = Math.abs(v);
    if (abs >= 1000000) return 'USD ' + new Intl.NumberFormat('de-DE', {minimumFractionDigits:1,maximumFractionDigits:1}).format(v/1000000) + 'M';
    if (abs >= 1000)    return 'USD ' + new Intl.NumberFormat('de-DE').format(Math.round(v/1000)) + 'K';
    return 'USD ' + new Intl.NumberFormat('de-DE', {minimumFractionDigits:2, maximumFractionDigits:2}).format(v);
  }
  function fmtPct(v) { return (v >= 0 ? '+' : '') + v.toFixed(1) + '%'; }

  /* ── Equivalente en USD (pre-calculado en backend) ─────────────────────── */
  /* Cada movimiento trae su campo `monto_usd` ya calculado al momento de
     guardarse, usando la cotización histórica del día correspondiente. La
     analítica consume ese valor directamente, sin conversión on-the-fly. */
  function mUSD(mv) {
    return (mv && mv.monto_usd != null) ? mv.monto_usd : 0;
  }

  /* Para el costo de envío: se sigue guardando en la moneda del movimiento.
     En USD queda tal cual; en ARS se prorratea usando la misma cotización que
     se aplicó al monto principal (derivada de monto_usd / monto). */
  function envUSD(mv) {
    if (!mv || !mv.costo_envio) return 0;
    if (mv.moneda === 'usd') return mv.costo_envio;
    if (!mv.monto || mv.monto === 0) return 0;
    return mv.costo_envio * (mv.monto_usd / mv.monto);
  }

  /* ── Mes helpers ────────────────────────────────────────────────────────── */
  var HOY = new Date();
  var mesAno = { anio: HOY.getFullYear(), mes: HOY.getMonth() + 1 };
  var NOM = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

  function mk(m)  { return m.anio + '-' + String(m.mes).padStart(2,'0'); }
  function ml(m)  { return NOM[m.mes-1] + ' ' + m.anio; }
  function ma(m)  { return NOM[m.mes-1].slice(0,3) + ' ' + String(m.anio).slice(2); }
  function mAnt(m){ return m.mes===1 ? {anio:m.anio-1,mes:12} : {anio:m.anio,mes:m.mes-1}; }
  function mSig(m){ return m.mes===12? {anio:m.anio+1,mes:1 } : {anio:m.anio,mes:m.mes+1}; }
  function esHoy(m){ return m.anio===HOY.getFullYear() && m.mes===HOY.getMonth()+1; }

  function ult6() {
    var r = [];
    for (var i=5; i>=0; i--) { var d=new Date(HOY.getFullYear(),HOY.getMonth()-i,1); r.push({anio:d.getFullYear(),mes:d.getMonth()+1}); }
    return r;
  }
  var MESES6 = ult6();

  /* ── Cálculo por mes ────────────────────────────────────────────────────── */
  function movMes(m) {
    var k = mk(m);
    return MOVIMIENTOS.filter(function(mv){ return mv.fecha.startsWith(k); });
  }

  function calcMes(m) {
    var mm = movMes(m);

    /* Suma USD-equivalente por tipo, sumando ARS y USD juntos */
    function sumaTipo(t) {
      return mm.filter(function(v){ return v.tipo===t && v.categoria!=='Cambio'; })
               .reduce(function(a,v){ return a + mUSD(v); }, 0);
    }

    var catMap = {};
    mm.filter(function(v){ return v.tipo==='gasto' && v.categoria!=='Cambio'; })
      .forEach(function(v){ var c=v.categoria||'Sin categoría'; catMap[c]=(catMap[c]||0)+mUSD(v); });

    var perMap = {};
    mm.filter(function(v){ return v.tipo==='gasto' && v.categoria!=='Cambio'; })
      .forEach(function(v){ perMap[v.persona]=(perMap[v.persona]||0)+mUSD(v); });

    var envio = mm.reduce(function(a,v){ return a + envUSD(v); }, 0);
    var envioCnt = mm.filter(function(v){ return v.costo_envio && v.costo_envio > 0; }).length;

    var fijosTotal = mm.filter(function(v){ return v.tipo==='gasto' && v.categoria==='Fijo'; })
      .reduce(function(a,v){ return a + mUSD(v); }, 0);

    return {
      ingUSD: sumaTipo('ingreso'), gasUSD: sumaTipo('gasto'),
      categorias: catMap, personas: perMap,
      envio: envio, envioCnt: envioCnt,
      fijosTotal: fijosTotal
    };
  }

  /* ══════════════════════════════════════════════════════════════════════════
     CHART.JS — Global config
     ══════════════════════════════════════════════════════════════════════════ */
  Chart.defaults.font.family = "'Segoe UI', system-ui, -apple-system, sans-serif";

  /* ── Secciones opcionales ─────────────────────────────────────────────────
     /personal esconde "Gastos fijos" (los fijos son del fondo familiar), asi
     que ese canvas y esos KPIs no existen ahi. Sin esto, el primer
     getContext() sobre null cortaba el script entero y se caia TODO el
     dashboard, no solo esa seccion. */
  var HAY_FIJOS = !!document.getElementById('chart-fijos');

  /* Escribe en un elemento solo si esta en la pagina. */
  function txt(id, valor) {
    var el = document.getElementById(id);
    if (el) el.textContent = valor;
  }

  /* ── SECCIÓN 1: Evolución de saldos ──────────────────────────────────── */

  /* Barras: ingresos vs gastos */
  var ctx1 = document.getElementById('chart-evolucion').getContext('2d');
  new Chart(ctx1, {
    type: 'bar',
    data: {
      labels: MESES6.map(ma),
      datasets: [
        { label:'Ingresos', data:MESES6.map(function(m){return calcMes(m).ingUSD;}),
          backgroundColor:C.exito+'b8', borderColor:C.exito, borderWidth:1, borderRadius:4 },
        { label:'Gastos', data:MESES6.map(function(m){return calcMes(m).gasUSD;}),
          backgroundColor:C.peligro+'b8', borderColor:C.peligro, borderWidth:1, borderRadius:4 }
      ]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{position:'bottom',labels:{usePointStyle:true,pointStyle:'circle',font:{size:11}}},
                tooltip:{callbacks:{label:function(c){return '  '+c.dataset.label+': '+fmtUSD(c.raw);}}} },
      scales:{
        y:{beginAtZero:true,ticks:{callback:fmtCorto,font:{size:10}},grid:{color:C.borde+'60'}},
        x:{ticks:{font:{size:10}},grid:{display:false}}
      }
    }
  });

  /* Gasto por persona — horizontal */
  var ctx2 = document.getElementById('chart-personas').getContext('2d');
  var chartPersonas = new Chart(ctx2, {
    type: 'bar',
    data: {
      labels: ['Elías','Mari'],
      datasets: [{ data:[0,0], backgroundColor:[C.elias+'cc',C.mari+'cc'],
                    borderColor:[C.elias,C.mari], borderWidth:1, borderRadius:6, barPercentage:0.55 }]
    },
    options: {
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false},
                tooltip:{callbacks:{label:function(c){return '  '+fmtUSD(c.raw);}}} },
      scales:{
        x:{beginAtZero:true,ticks:{callback:fmtCorto,font:{size:10}},grid:{color:C.borde+'60'}},
        y:{ticks:{font:{size:12,weight:'600'}},grid:{display:false}}
      }
    }
  });

  /* Tendencia de ahorro (neto mensual) */
  var datNeto = MESES6.map(function(m){ var d=calcMes(m); return d.ingUSD - d.gasUSD; });
  var ctx3 = document.getElementById('chart-ahorro').getContext('2d');
  new Chart(ctx3, {
    type: 'line',
    data: {
      labels: MESES6.map(ma),
      datasets: [{
        label:'Ahorro neto', data:datNeto,
        borderColor:C.acento, backgroundColor:C.acento+'18', fill:true, tension:0.35,
        pointRadius:5, pointBackgroundColor:C.acento, pointBorderColor:C.superficie, pointBorderWidth:2, borderWidth:2.5
      },{
        label:'Línea base (USD 0)', data:MESES6.map(function(){return 0;}),
        borderColor:C.textoS, borderDash:[6,4], borderWidth:1.5, pointRadius:0, fill:false
      }]
    },
    options: {
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{position:'bottom',labels:{usePointStyle:true,pointStyle:'circle',font:{size:11}}},
                tooltip:{callbacks:{label:function(c){return '  '+c.dataset.label+': '+fmtUSD(c.raw);}}} },
      scales:{
        y:{ticks:{callback:fmtCorto,font:{size:10}},grid:{color:C.borde+'60'}},
        x:{ticks:{font:{size:10}},grid:{display:false}}
      }
    }
  });

  /* ── SECCIÓN 2: Sueldos ─────────────────────────────────────────────── */

  /* Sueldo por persona — evolución 6 meses (Elías vs Mari). Solo categoría 'Sueldo'. */
  function sueldoMes(m, persona) {
    var k = mk(m);
    return MOVIMIENTOS.filter(function(mv){
      return mv.fecha.startsWith(k) && mv.tipo==='ingreso' && mv.categoria==='Sueldo' && mv.persona===persona;
    }).reduce(function(a,v){ return a + mUSD(v); }, 0);
  }

  var ctxSueldo = document.getElementById('chart-sueldo-persona').getContext('2d');
  new Chart(ctxSueldo, {
    type:'line',
    data:{
      labels: MESES6.map(ma),
      datasets:[
        { label:'Elías', data:MESES6.map(function(m){return sueldoMes(m,'elias');}),
          borderColor:C.elias, backgroundColor:C.elias+'20', fill:false, tension:0.3,
          pointRadius:4, pointBackgroundColor:C.elias, pointBorderColor:C.superficie, pointBorderWidth:2, borderWidth:2 },
        { label:'Mari', data:MESES6.map(function(m){return sueldoMes(m,'mari');}),
          borderColor:C.mari, backgroundColor:C.mari+'20', fill:false, tension:0.3,
          pointRadius:4, pointBackgroundColor:C.mari, pointBorderColor:C.superficie, pointBorderWidth:2, borderWidth:2 }
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{position:'bottom',labels:{usePointStyle:true,pointStyle:'circle',font:{size:11}}},
                tooltip:{callbacks:{label:function(c){return '  '+c.dataset.label+': '+fmtUSD(c.raw);}}} },
      scales:{
        y:{beginAtZero:true,ticks:{callback:fmtCorto,font:{size:10}},grid:{color:C.borde+'60'}},
        x:{ticks:{font:{size:10}},grid:{display:false}}
      }
    }
  });

  /* ── SECCIÓN 3: Gastos por categoría ────────────────────────────────── */

  /* Donut de categorías */
  var ctx4 = document.getElementById('chart-cat-donut').getContext('2d');
  var chartDonut = new Chart(ctx4, {
    type:'doughnut',
    data:{ labels:[], datasets:[{ data:[], backgroundColor:PALETA, borderWidth:2, borderColor:C.superficie, hoverOffset:8 }] },
    options:{
      responsive:true, maintainAspectRatio:false, cutout:'62%',
      plugins:{
        legend:{position:'bottom',labels:{font:{size:10},usePointStyle:true,pointStyle:'circle',padding:10}},
        tooltip:{callbacks:{label:function(c){
          var t=c.dataset.data.reduce(function(a,b){return a+b;},0);
          return '  '+c.label+': '+fmtUSD(c.raw)+' ('+(t>0?((c.raw/t)*100).toFixed(1):0)+'%)';
        }}}
      }
    }
  });

  /* Evolución por categoría (seleccionable) */
  var ctx5 = document.getElementById('chart-cat-evolucion').getContext('2d');
  var chartCatEvol = new Chart(ctx5, {
    type:'line', data:{ labels:MESES6.map(ma), datasets:[] },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false},
                tooltip:{callbacks:{label:function(c){return '  '+c.dataset.label+': '+fmtUSD(c.raw);}}} },
      scales:{
        y:{beginAtZero:true,ticks:{callback:fmtCorto,font:{size:10}},grid:{color:C.borde+'60'}},
        x:{ticks:{font:{size:10}},grid:{display:false}}
      }
    }
  });

  /* Detectar todas las categorías existentes (excluyendo Cambio).
     Incluimos movimientos en AR$ y USD — todo se muestra en USD. */
  var allCats = {};
  MOVIMIENTOS.forEach(function(mv){
    if (mv.tipo==='gasto' && mv.categoria && mv.categoria!=='Cambio') {
      allCats[mv.categoria] = true;
    }
  });
  var catList = Object.keys(allCats).sort();
  var catActivas = {};
  /* Activar top 3 por defecto (totales en USD) */
  var catTotals = {};
  catList.forEach(function(c){ catTotals[c]=0; });
  MOVIMIENTOS.forEach(function(mv){
    if (mv.tipo==='gasto' && mv.categoria && mv.categoria!=='Cambio')
      catTotals[mv.categoria] = (catTotals[mv.categoria]||0) + mUSD(mv);
  });
  var catSorted = catList.slice().sort(function(a,b){return catTotals[b]-catTotals[a];});
  catSorted.slice(0,3).forEach(function(c){ catActivas[c]=true; });

  function renderCatToggles() {
    var cont = document.getElementById('cat-toggles');
    cont.innerHTML = '';
    catList.forEach(function(cat, idx) {
      var btn = document.createElement('button');
      btn.className = 'dash-toggle-btn' + (catActivas[cat] ? ' activo' : '');
      btn.textContent = cat;
      btn.style.borderColor = PALETA[idx % PALETA.length];
      if (catActivas[cat]) btn.style.backgroundColor = PALETA[idx % PALETA.length];
      btn.addEventListener('click', function() {
        catActivas[cat] = !catActivas[cat];
        renderCatToggles();
        actualizarCatEvol();
      });
      cont.appendChild(btn);
    });
  }

  function actualizarCatEvol() {
    var datasets = [];
    catList.forEach(function(cat, idx) {
      if (!catActivas[cat]) return;
      var color = PALETA[idx % PALETA.length];
      datasets.push({
        label: cat,
        data: MESES6.map(function(m) {
          var k = mk(m);
          return MOVIMIENTOS.filter(function(mv){
            return mv.fecha.startsWith(k) && mv.tipo==='gasto' && mv.categoria===cat;
          }).reduce(function(a,v){return a + mUSD(v);},0);
        }),
        borderColor: color, backgroundColor: color+'20', fill:false,
        tension:0.3, pointRadius:4, pointBackgroundColor:color,
        pointBorderColor:C.superficie, pointBorderWidth:2, borderWidth:2
      });
    });
    chartCatEvol.data.datasets = datasets;
    chartCatEvol.update();
  }

  renderCatToggles();

  /* ── SECCIÓN 4: Envíos ──────────────────────────────────────────────── */
  var ctx6 = document.getElementById('chart-envios').getContext('2d');
  var envioData = MESES6.map(function(m) {
    var k = mk(m);
    return MOVIMIENTOS.filter(function(mv){ return mv.fecha.startsWith(k); })
      .reduce(function(a,v){ return a + envUSD(v); }, 0);
  });

  new Chart(ctx6, {
    type:'bar',
    data:{
      labels:MESES6.map(ma),
      datasets:[{ label:'Costos de envío', data:envioData,
                   backgroundColor:C.alerta+'aa', borderColor:C.alerta, borderWidth:1, borderRadius:4 }]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false},
                tooltip:{callbacks:{label:function(c){return '  Envíos: '+fmtUSD(c.raw);}}} },
      scales:{
        y:{beginAtZero:true,ticks:{callback:fmtCorto,font:{size:10}},grid:{color:C.borde+'60'}},
        x:{ticks:{font:{size:10}},grid:{display:false}}
      }
    }
  });

  /* ── SECCIÓN 5: Gastos fijos (seleccionable) ─────────────────────────── */
  /* Detectamos descripciones de fijos en cualquier moneda — todo va a USD. */
  var fijosDescs = [];
  MOVIMIENTOS.forEach(function(mv){
    if (mv.categoria==='Fijo' && fijosDescs.indexOf(mv.descripcion)===-1)
      fijosDescs.push(mv.descripcion);
  });
  fijosDescs.sort();
  var fijosActivos = {};
  /* Activar top 3 por monto en USD */
  var fijosTotals = {};
  fijosDescs.forEach(function(f){ fijosTotals[f]=0; });
  MOVIMIENTOS.forEach(function(mv){
    if (mv.categoria==='Fijo') fijosTotals[mv.descripcion]=(fijosTotals[mv.descripcion]||0)+mUSD(mv);
  });
  var fijosSorted = fijosDescs.slice().sort(function(a,b){return fijosTotals[b]-fijosTotals[a];});
  fijosSorted.slice(0,3).forEach(function(f){ fijosActivos[f]=true; });

  var chartFijos = HAY_FIJOS && new Chart(document.getElementById('chart-fijos').getContext('2d'), {
    type:'line', data:{ labels:MESES6.map(ma), datasets:[] },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false},
                tooltip:{callbacks:{label:function(c){return '  '+c.dataset.label+': '+fmtUSD(c.raw);}}} },
      scales:{
        y:{beginAtZero:true,ticks:{callback:fmtCorto,font:{size:10}},grid:{color:C.borde+'60'}},
        x:{ticks:{font:{size:10}},grid:{display:false}}
      }
    }
  });

  function renderFijosToggles() {
    var cont = document.getElementById('fijos-toggles');
    if (!cont) return;
    cont.innerHTML = '';
    fijosDescs.forEach(function(desc, idx) {
      var btn = document.createElement('button');
      btn.className = 'dash-toggle-btn' + (fijosActivos[desc] ? ' activo' : '');
      btn.textContent = desc;
      btn.style.borderColor = PALETA[idx % PALETA.length];
      if (fijosActivos[desc]) btn.style.backgroundColor = PALETA[idx % PALETA.length];
      btn.addEventListener('click', function() {
        fijosActivos[desc] = !fijosActivos[desc];
        renderFijosToggles();
        actualizarFijos();
      });
      cont.appendChild(btn);
    });
  }

  function actualizarFijos() {
    if (!chartFijos) return;
    var datasets = [];
    fijosDescs.forEach(function(desc, idx) {
      if (!fijosActivos[desc]) return;
      var color = PALETA[idx % PALETA.length];
      datasets.push({
        label: desc,
        data: MESES6.map(function(m) {
          var k = mk(m);
          return MOVIMIENTOS.filter(function(mv){
            return mv.fecha.startsWith(k) && mv.categoria==='Fijo' && mv.descripcion===desc;
          }).reduce(function(a,v){return a + mUSD(v);},0);
        }),
        borderColor:color, backgroundColor:color+'20', fill:false,
        tension:0.3, pointRadius:4, pointBackgroundColor:color,
        pointBorderColor:C.superficie, pointBorderWidth:2, borderWidth:2
      });
    });
    chartFijos.data.datasets = datasets;
    chartFijos.update();
  }

  renderFijosToggles();

  /* ══════════════════════════════════════════════════════════════════════════
     ACTUALIZACIÓN GLOBAL AL CAMBIAR MES
     ══════════════════════════════════════════════════════════════════════════ */
  function actualizarTodo(m) {
    var d = calcMes(m);
    var dAnt = calcMes(mAnt(m));

    document.getElementById('titulo-mes').textContent = ml(m);
    document.getElementById('btn-mes-sig').disabled = esHoy(m);

    /* KPIs evolución (todo en USD) */
    document.getElementById('kpi-ingresos').textContent = fmtUSD(d.ingUSD);
    document.getElementById('kpi-ingresos').className = 'dash-kpi-valor texto-positivo';

    document.getElementById('kpi-gastos').textContent = fmtUSD(d.gasUSD);
    if (dAnt.gasUSD > 0) {
      var v = ((d.gasUSD - dAnt.gasUSD) / dAnt.gasUSD) * 100;
      var sub = document.getElementById('kpi-gastos-sub');
      sub.textContent = fmtPct(v) + ' vs mes ant.';
      sub.className = 'dash-kpi-sub ' + (v <= 0 ? 'dash-kpi-sub-ok' : 'dash-kpi-sub-warn');
    } else {
      document.getElementById('kpi-gastos-sub').textContent = '';
    }

    var neto = d.ingUSD - d.gasUSD;
    var netoEl = document.getElementById('kpi-neto');
    netoEl.textContent = fmtUSD(neto);
    netoEl.className = 'dash-kpi-valor ' + (neto >= 0 ? 'texto-positivo' : 'texto-negativo');

    var ahEl = document.getElementById('kpi-ahorro');
    if (d.ingUSD > 0) {
      var tasa = ((d.ingUSD - d.gasUSD) / d.ingUSD) * 100;
      ahEl.textContent = tasa.toFixed(1) + '%';
      ahEl.className = 'dash-kpi-valor ' + (tasa >= 0 ? 'texto-positivo' : 'texto-negativo');
    } else {
      ahEl.textContent = '—';
      ahEl.className = 'dash-kpi-valor';
    }

    /* Personas */
    chartPersonas.data.datasets[0].data = [d.personas['elias']||0, d.personas['mari']||0];
    chartPersonas.update();
    document.getElementById('persona-titulo').textContent = 'Gasto por persona · ' + ma(m);

    /* Donut categorías */
    var cats = Object.keys(d.categorias).sort(function(a,b){return d.categorias[b]-d.categorias[a];});
    chartDonut.data.labels = cats;
    chartDonut.data.datasets[0].data = cats.map(function(c){return d.categorias[c];});
    chartDonut.update();
    var totalCat = cats.reduce(function(a,c){return a+d.categorias[c];},0);
    var centro = document.getElementById('cat-donut-centro');
    centro.innerHTML = totalCat > 0
      ? '<span class="donut-pct">' + fmtCorto(totalCat) + '</span><span class="donut-pct-label">total</span>'
      : '<span class="donut-sin-datos">Sin datos</span>';
    document.getElementById('cat-donut-titulo').textContent = 'Distribución · ' + ma(m);

    /* Ranking categorías */
    var rc = document.getElementById('ranking-categorias');
    rc.innerHTML = '';
    if (cats.length === 0) { rc.innerHTML = '<div class="dash-ranking-vacio">Sin gastos este mes</div>'; }
    else {
      var maxV = d.categorias[cats[0]];
      cats.forEach(function(cat, i) {
        var monto = d.categorias[cat];
        var pct = totalCat > 0 ? ((monto/totalCat)*100).toFixed(1) : 0;
        var bw = maxV > 0 ? ((monto/maxV)*100).toFixed(1) : 0;
        var row = document.createElement('div'); row.className = 'dash-ranking-row';
        row.innerHTML =
          '<div class="dash-ranking-pos">'+(i+1)+'</div>' +
          '<div class="dash-ranking-info">' +
            '<div class="dash-ranking-header"><span class="dash-ranking-cat">'+cat+'</span><span class="dash-ranking-monto">'+fmtUSD(monto)+'</span></div>' +
            '<div class="dash-ranking-bar-bg"><div class="dash-ranking-bar" style="width:'+bw+'%;background:'+PALETA[i%PALETA.length]+'"></div></div>' +
            '<div class="dash-ranking-pct">'+pct+'% del total</div>' +
          '</div>';
        rc.appendChild(row);
      });
    }
    document.getElementById('ranking-titulo').textContent = 'Ranking · ' + ma(m);

    /* Evolución por categoría */
    actualizarCatEvol();

    /* Envíos (en USD) */
    document.getElementById('kpi-envio-mes').textContent = fmtUSD(d.envio);
    document.getElementById('kpi-envio-cant').textContent = d.envioCnt + ' envío' + (d.envioCnt !== 1 ? 's' : '');
    var totalEnvio = MOVIMIENTOS.reduce(function(a,v){return a + envUSD(v);},0);
    var totalEnvioCnt = MOVIMIENTOS.filter(function(v){return v.costo_envio&&v.costo_envio>0;}).length;
    document.getElementById('kpi-envio-total').textContent = fmtUSD(totalEnvio);
    document.getElementById('kpi-envio-total-cant').textContent = totalEnvioCnt + ' envío' + (totalEnvioCnt !== 1 ? 's' : '') + ' en total';

    /* Gastos fijos KPI (en USD) */
    txt('kpi-fijos-mes', fmtUSD(d.fijosTotal));
    txt('kpi-fijos-pct', d.ingUSD > 0 ? ((d.fijosTotal / d.ingUSD) * 100).toFixed(1) + '%' : '—');

    /* Fijos evolución */
    actualizarFijos();
  }

  /* ── Navegación de mes ──────────────────────────────────────────────── */
  document.getElementById('btn-mes-ant').addEventListener('click', function() {
    mesAno = mAnt(mesAno); actualizarTodo(mesAno);
  });
  document.getElementById('btn-mes-sig').addEventListener('click', function() {
    if (!esHoy(mesAno)) { mesAno = mSig(mesAno); actualizarTodo(mesAno); }
  });

  actualizarTodo(mesAno);
}());
