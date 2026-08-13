from services.a2_retrieval_service import retrieve_relevant_entries

KB = [
    {
        "id": "KB01",
        "title": "Şifre sıfırlama",
        "content": "Şifrenizi sıfırlamak için giriş ekranındaki 'Şifremi Unuttum' bağlantısına tıklayın.",
        "role": ["learner"],
        "product_area": "authentication",
        "status": "approved",
        "version": "1.0",
        "last_updated": "2026-07-01",
    },
    {
        "id": "KB02",
        "title": "Quiz tekrar hakkı",
        "content": "Bir quiz için toplam 3 deneme hakkı bulunur.",
        "role": ["learner"],
        "product_area": "quiz",
        "status": "approved",
        "version": "1.0",
        "last_updated": "2026-07-01",
    },
    {
        "id": "KB03",
        "title": "Taslak: yayınlanmamış madde",
        "content": "Şifre ile ilgili taslak bir içerik, henüz onaylanmadı.",
        "role": ["trainer"],
        "product_area": "authentication",
        "status": "draft",
        "version": "0.1",
        "last_updated": "2026-06-01",
    },
]


def test_only_approved_entries_are_considered():
    results, sufficient = retrieve_relevant_entries("şifre ile ilgili taslak sorun", KB)
    ids = [r["id"] for r in results]
    assert "KB03" not in ids


def test_lexical_retrieval_finds_relevant_entry():
    results, sufficient = retrieve_relevant_entries("Şifremi unuttum, ne yapmalıyım?", KB)
    assert sufficient is True
    assert results[0]["id"] == "KB01"


def test_no_result_retrieval_returns_empty_and_insufficient():
    results, sufficient = retrieve_relevant_entries("bugün hava nasıl olacak", KB)
    assert results == []
    assert sufficient is False


def test_retrieval_scores_are_included():
    results, sufficient = retrieve_relevant_entries("quiz tekrar hakkı kaç", KB)
    assert sufficient is True
    assert all("score" in r for r in results)
    assert results[0]["score"] > 0
