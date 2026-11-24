import { useMemo, useRef, useState } from "react";

const matchLabels = {
  exact_name_match: "Tam ad eşleşmesi", token_name_match: "Ad-soyad eşleşmesi",
  probable_name_match: "Muhtemel eşleşme", surname_only: "Yalnız soyad",
  no_name_match: "Eşleşme yok", public_name_missing: "Kamuya açık ad yok",
  checksum_invalid: "Checksum geçersiz", api_not_found: "API kaydı bulunamadı",
  api_api_error: "API hatası", api_network_error: "Ağ hatası",
};

function Status({ value }) {
  const tone = value?.includes("match") && !value.includes("no_") ? "good" : value === "surname_only" || value === "checksum_invalid" ? "warn" : "neutral";
  return <span className={`status ${tone}`}>{matchLabels[value] ?? value ?? "Bilinmiyor"}</span>;
}

function formatSize(bytes) { return `${(bytes / 1024 / 1024).toFixed(1)} MB`; }

export default function App() {
  const [data, setData] = useState(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const fileInput = useRef(null);

  const chooseFiles = (event) => {
    const files = Array.from(event.target.files ?? []);
    setError("");
    if (files.length > 10) {
      setSelectedFiles(files.slice(0, 10));
      setError("İlk 10 PDF seçildi; tek analizde en fazla 10 dosya yüklenebilir.");
    } else setSelectedFiles(files);
  };

  const openFilePicker = () => fileInput.current?.click();

  const reset = () => {
    setData(null); setSelected(null); setSelectedFiles([]); setError(""); setFilter("all");
    if (fileInput.current) fileInput.current.value = "";
  };

  const analyze = async () => {
    if (!selectedFiles.length) { setError("Önce en az bir PDF seç."); return; }
    setLoading(true); setError(""); setSelected(null);
    try {
      const form = new FormData();
      selectedFiles.forEach((file) => form.append("files", file));
      const response = await fetch("/api/analyze-orcid", { method: "POST", body: form });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Analiz başlatılamadı.");
      setData(payload); setFilter("all");
    } catch (caught) {
      setError(caught.message || "Beklenmeyen bir hata oluştu.");
    } finally { setLoading(false); }
  };

  const rows = useMemo(() => (data?.results ?? []).filter((row) => filter === "all" || row.name_match_status === filter), [data, filter]);
  const filters = useMemo(() => ["all", ...Array.from(new Set((data?.results ?? []).map((row) => row.name_match_status)))], [data]);

  return <main>
    <section className="hero">
      <div><p className="eyebrow">AKADEMİK PDF METADATA PİLOTU</p><h1>ORCID Doğrulama Merkezi</h1><p className="subhead">En fazla 10 dijital PDF yükle. ORCID’ler metin ve bağlantılardan çıkarılır; biçim, kayıt ve yazar adı eşleşmesi tek analizde kontrol edilir.</p></div>
      {data && <button className="refresh" onClick={reset}>Yeni analiz</button>}
    </section>

    <section className="flow" aria-label="Doğrulama aşamaları">
      <div><b>1</b><span>PDF’den çıkarım</span><small>Metin ve bağlantı taraması</small></div>
      <div><b>2</b><span>Yapısal kontrol</span><small>ORCID biçimi ve checksum</small></div>
      <div><b>3</b><span>Kayıt sorgusu</span><small>ORCID Public API</small></div>
      <div><b>4</b><span>Ad eşleştirme</span><small>PDF metni ve ORCID adı</small></div>
    </section>

    {!data && <section className="upload-panel">
      <p className="eyebrow">GEÇİCİ ANALİZ</p><h2>PDF’lerini seç, sonucu burada gör.</h2>
      <p>Dosyalar yalnızca analiz boyunca geçici alanda tutulur. Sayfayı yenilediğinde veya yeni analiz başlattığında ekrandaki sonuçlar sıfırlanır.</p>
      <div className="dropzone">
        <input ref={fileInput} type="file" accept="application/pdf,.pdf" multiple onChange={chooseFiles} />
        <button type="button" className="file-select" onClick={openFilePicker}>PDF seç</button>
        <small>En fazla 10 dosya · dosya başına en fazla 8 MB</small>
      </div>
      {selectedFiles.length > 0 && <ul className="file-list">{selectedFiles.map((file) => <li key={`${file.name}-${file.lastModified}`}><span>{file.name}</span><small>{formatSize(file.size)}</small></li>)}</ul>}
      <button className="analyze" onClick={analyze} disabled={loading || !selectedFiles.length}>{loading ? "Analiz ediliyor…" : `${selectedFiles.length || 0} PDF'yi analiz et`}</button>
      {error && <p className="error">{error}</p>}
    </section>}

    {data && <>
      <section className="metrics">
        <article><span>ORCID aday kaydı</span><strong>{data.summary.candidates}</strong><small>PDF metni veya bağlantısından</small></article>
        <article><span>Checksum geçerli</span><strong>{data.summary.checksum_valid}</strong><small>Yapısal olarak tutarlı ID</small></article>
        <article><span>API kaydı bulundu</span><strong>{data.summary.api_found}</strong><small>ORCID Public API sonucu</small></article>
        <article><span>Olumlu ad eşleşmesi</span><strong>{data.summary.positive_matches}</strong><small>Tam, token veya muhtemel</small></article>
      </section>
      <section className="file-summary"><strong>{data.summary.analyzed_pdfs}/{data.summary.uploaded_pdfs} PDF analiz edildi</strong>{data.file_results.map((file) => <span key={file.pdf} className={file.status === "analyzed" ? "file-ok" : "file-bad"}>{file.pdf}: {file.message}</span>)}</section>
      <section className="panel"><div className="panel-head"><div><p className="eyebrow">DENETİM TABLOSU</p><h2>Yazar adı karşılaştırmaları</h2></div><div className="filters">{filters.map((item) => <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item === "all" ? "Tümü" : (matchLabels[item] ?? item)}</button>)}</div></div>
        <div className="table-wrap"><table><thead><tr><th>PDF</th><th>Sayfa</th><th>ORCID</th><th>API’deki ad</th><th>Sonuç</th><th></th></tr></thead><tbody>
          {rows.map((row, index) => <tr key={`${row.pdf}-${row.orcid}-${index}`}><td>{row.pdf}</td><td>{row.page}</td><td className="mono">{row.orcid}</td><td>{row.orcid_public_name || "—"}</td><td><Status value={row.name_match_status} /></td><td><button className="detail" onClick={() => setSelected(row)}>İncele</button></td></tr>)}
          {!rows.length && <tr><td colSpan="6" className="no-rows">Bu filtrede sonuç yok.</td></tr>}
        </tbody></table></div>
      </section>
    </>}

    {selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><section className="modal" onClick={(event) => event.stopPropagation()}>
      <button className="close" onClick={() => setSelected(null)}>Kapat</button><p className="eyebrow">EŞLEŞME DETAYI</p><h2>{selected.orcid}</h2><Status value={selected.name_match_status} />
      <dl><dt>API’deki ad</dt><dd>{selected.orcid_public_name || "Kamuya açık değil"}</dd><dt>Açıklama</dt><dd>{selected.explanation}</dd><dt>PDF bağlamı</dt><dd>{selected.orcid_context}</dd><dt>Sayfa metni</dt><dd>{selected.page_text_excerpt}</dd></dl>
    </section></div>}
  </main>;
}
