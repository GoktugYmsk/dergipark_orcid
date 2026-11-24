import { useEffect, useMemo, useState } from "react";

const files = {
  candidates: "/data/orcid_candidates.csv",
  api: "/data/orcid_api_validation.csv",
  matches: "/data/orcid_author_name_matches.csv",
};

function parseCsv(text) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"' && quoted && next === '"') { cell += '"'; index += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === "," && !quoted) { row.push(cell); cell = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(cell);
      if (row.some((value) => value.length)) rows.push(row);
      row = []; cell = "";
    } else cell += char;
  }
  if (cell.length || row.length) { row.push(cell); rows.push(row); }
  const [headers = [], ...values] = rows;
  return values.map((valuesRow) => Object.fromEntries(headers.map((header, i) => [header, valuesRow[i] ?? ""])));
}

async function loadCsv(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} bulunamadı`);
  return parseCsv(await response.text());
}

const matchLabels = {
  exact_name_match: "Tam ad eşleşmesi",
  token_name_match: "Ad-soyad eşleşmesi",
  probable_name_match: "Muhtemel eşleşme",
  surname_only: "Yalnız soyad",
  no_name_match: "Eşleşme yok",
  public_name_missing: "Kamuya açık ad yok",
  api_not_found: "API kaydı bulunamadı",
  api_api_error: "API hatası",
  api_network_error: "Ağ hatası",
  pdf_missing: "PDF bulunamadı",
};

const positiveStatuses = new Set(["exact_name_match", "token_name_match", "probable_name_match"]);

function Status({ value }) {
  const tone = value?.includes("match") && !value.includes("no_") ? "good" :
    value === "surname_only" ? "warn" : "neutral";
  return <span className={`status ${tone}`}>{matchLabels[value] ?? value ?? "Bilinmiyor"}</span>;
}

function App() {
  const [data, setData] = useState({ candidates: [], api: [], matches: [] });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState(null);

  const refresh = async () => {
    setLoading(true); setError("");
    try {
      const [candidates, api, matches] = await Promise.all([loadCsv(files.candidates), loadCsv(files.api), loadCsv(files.matches)]);
      setData({ candidates, api, matches });
    } catch (caught) { setError(caught.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { refresh(); }, []);

  const summary = useMemo(() => {
    const valid = data.candidates.filter((row) => row.checksum_valid === "True").length;
    const found = data.api.filter((row) => row.api_status === "found").length;
    const positive = data.matches.filter((row) => positiveStatuses.has(row.name_match_status)).length;
    return { candidates: data.candidates.length, valid, found, positive };
  }, [data]);

  const rows = data.matches.filter((row) => filter === "all" || row.name_match_status === filter);
  const filters = ["all", ...Array.from(new Set(data.matches.map((row) => row.name_match_status)))];

  return <main>
    <section className="hero">
      <div>
        <p className="eyebrow">AKADEMİK PDF METADATA PİLOTU</p>
        <h1>ORCID Doğrulama Merkezi</h1>
        <p className="subhead">PDF içindeki ORCID’leri çıkarır, yapısal olarak doğrular, ORCID kaydını kontrol eder ve kamuya açık adı kaynak sayfadaki metinle karşılaştırır.</p>
      </div>
      <button className="refresh" onClick={refresh}>Veriyi yenile</button>
    </section>

    <section className="flow" aria-label="Doğrulama aşamaları">
      <div><b>1</b><span>PDF’den çıkarım</span><small>Metin ve bağlantı taraması</small></div>
      <div><b>2</b><span>Yapısal kontrol</span><small>ORCID biçimi ve checksum</small></div>
      <div><b>3</b><span>Kayıt sorgusu</span><small>ORCID Public API</small></div>
      <div><b>4</b><span>Ad eşleştirme</span><small>PDF metni ve ORCID adı</small></div>
    </section>

    {error ? <section className="empty"><h2>Henüz görüntülenecek veri yok</h2><p>Önce terminalde <code>python run_orcid_pipeline.py</code>, ardından bu klasörde <code>npm run sync-data</code> çalıştır.</p><p className="muted">Ayrıntı: {error}</p></section> : <>
      <section className="metrics">
        <article><span>ORCID aday kaydı</span><strong>{summary.candidates}</strong><small>PDF metni veya bağlantısından</small></article>
        <article><span>Checksum geçerli</span><strong>{summary.valid}</strong><small>Yapısal olarak tutarlı ID</small></article>
        <article><span>API kaydı bulundu</span><strong>{summary.found}</strong><small>ORCID Public API sonucu</small></article>
        <article><span>Olumlu ad eşleşmesi</span><strong>{summary.positive}</strong><small>Tam, token veya muhtemel</small></article>
      </section>

      <section className="panel">
        <div className="panel-head"><div><p className="eyebrow">DENETİM TABLOSU</p><h2>Yazar adı karşılaştırmaları</h2></div><div className="filters">
          {filters.map((item) => <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item === "all" ? "Tümü" : (matchLabels[item] ?? item)}</button>)}
        </div></div>
        {loading ? <p className="loading">Veriler yükleniyor…</p> : <div className="table-wrap"><table><thead><tr><th>PDF</th><th>Sayfa</th><th>ORCID</th><th>API’deki ad</th><th>Sonuç</th><th></th></tr></thead><tbody>
          {rows.map((row, index) => <tr key={`${row.pdf}-${row.orcid}-${index}`}><td>{row.pdf}</td><td>{row.page}</td><td className="mono">{row.orcid}</td><td>{row.orcid_public_name || "—"}</td><td><Status value={row.name_match_status} /></td><td><button className="detail" onClick={() => setSelected(row)}>İncele</button></td></tr>)}
        </tbody></table></div>}
      </section>
    </>}

    {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><section className="modal" onClick={(event) => event.stopPropagation()}>
      <button className="close" onClick={() => setSelected(null)}>Kapat</button><p className="eyebrow">EŞLEŞME DETAYI</p><h2>{selected.orcid}</h2><Status value={selected.name_match_status} />
      <dl><dt>API’deki ad</dt><dd>{selected.orcid_public_name || "Kamuya açık değil"}</dd><dt>Açıklama</dt><dd>{selected.explanation}</dd><dt>PDF bağlamı</dt><dd>{selected.orcid_context}</dd><dt>Sayfa metni</dt><dd>{selected.page_text_excerpt}</dd></dl>
    </section></div>}
  </main>;
}

export default App;
