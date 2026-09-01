use pyo3::prelude::*;
use lopdf::Document;
use regex::Regex;

#[pyfunction]
// Use &[u8] instead of Vec<u8> to avoid unnecessary copying and macro friction
fn extract_and_clean_pdf(file_bytes: &[u8]) -> PyResult<String> {
    // 1. Load the document from memory
    let doc = Document::load_mem(file_bytes)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("PDF Load Error: {}", e)))?;

    let mut full_text = String::new();

    // 2. Get all page numbers
    let pages = doc.get_pages();
    
    // Sort pages by page number to ensure text is in order
    let mut page_numbers: Vec<_> = pages.keys().collect();
    page_numbers.sort();

    for &page_num in page_numbers {
        if let Ok(text) = doc.extract_text(&[page_num]) {
            full_text.push_str(&text);
            full_text.push(' ');
        }
    }

    // 3. Clean the text using Regex
    let newline_re = Regex::new(r"\n+").unwrap();
    let space_re = Regex::new(r"\s+").unwrap();
    let page_re = Regex::new(r"Page \d+ of \d+").unwrap();

    let no_pages = page_re.replace_all(&full_text, "");
    let no_newlines = newline_re.replace_all(&no_pages, " ");
    let cleaned = space_re.replace_all(&no_newlines, " ");

    Ok(cleaned.trim().to_string())
}

#[pymodule]
fn rust_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_and_clean_pdf, m)?)?;
    Ok(())
}