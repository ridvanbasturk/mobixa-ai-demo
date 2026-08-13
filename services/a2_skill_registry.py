"""A2 için yetenek (skill) ve eklenti (plugin) kayıt defteri.

Bu, PoC'de gerçekten aktif olan yeteneklerle, ileride eklenebilecek ama
henüz gerçek bir Mobixa backend entegrasyonu olmayan eklentileri açıkça
birbirinden ayırır. Hiçbir eklenti gerçek bir işlem yürütmez.
"""
from __future__ import annotations

from typing import Dict, List

_ACTIVE_SKILLS_TR: List[str] = [
    "Yardım makalesi arama",
    "Kaynaklı cevap üretme",
    "Bilgi yetersizliğini tespit etme",
    "Prompt injection talimatlarını reddetme",
    "Destek yönlendirmesi önerme",
    "Kaynak ID doğrulama",
]

_ACTIVE_SKILLS_EN: List[str] = [
    "Help article search",
    "Grounded answer generation",
    "Detecting insufficient information",
    "Rejecting prompt injection instructions",
    "Suggesting support escalation",
    "Source id validation",
]

_FUTURE_PLUGINS_TR: List[Dict[str, str]] = [
    {
        "name": "Kullanıcı rolünü ve yetkilerini sorgulama",
        "purpose": "Kullanıcının rolüne (learner/trainer/admin) göre cevapları kişiselleştirmek.",
        "expected_input": "user_id",
        "expected_output": "role, permissions",
        "status": "Gelecek entegrasyon",
    },
    {
        "name": "Aktivite durumunu sorgulama",
        "purpose": "Belirli bir aktivitenin gerçek tamamlanma durumunu canlı olarak getirmek.",
        "expected_input": "activity_id",
        "expected_output": "status, completion_percentage",
        "status": "Gelecek entegrasyon",
    },
    {
        "name": "Atanmış eğitimleri listeleme",
        "purpose": "Kullanıcıya gerçek zamanlı olarak hangi eğitimlerin atandığını göstermek.",
        "expected_input": "user_id",
        "expected_output": "assigned_training_ids, due_dates",
        "status": "Gelecek entegrasyon",
    },
    {
        "name": "Destek talebi oluşturma",
        "purpose": "Chatbot'un yetersiz kaldığı durumlarda otomatik olarak bir destek talebi açmak.",
        "expected_input": "user_id, question, conversation_summary",
        "expected_output": "ticket_id",
        "status": "Gelecek entegrasyon",
    },
    {
        "name": "İlgili yardım sayfasını açma",
        "purpose": "Kullanıcıyı doğrudan ilgili yardım merkezi sayfasına yönlendirmek.",
        "expected_input": "topic_or_source_id",
        "expected_output": "help_center_url",
        "status": "Gelecek entegrasyon",
    },
]

_FUTURE_PLUGINS_EN: List[Dict[str, str]] = [
    {
        "name": "Look up user role and permissions",
        "purpose": "Personalize answers based on the user's role (learner/trainer/admin).",
        "expected_input": "user_id",
        "expected_output": "role, permissions",
        "status": "Future integration",
    },
    {
        "name": "Look up activity status",
        "purpose": "Fetch the real, live completion status of a specific activity.",
        "expected_input": "activity_id",
        "expected_output": "status, completion_percentage",
        "status": "Future integration",
    },
    {
        "name": "List assigned trainings",
        "purpose": "Show the user in real time which trainings are assigned to them.",
        "expected_input": "user_id",
        "expected_output": "assigned_training_ids, due_dates",
        "status": "Future integration",
    },
    {
        "name": "Create a support ticket",
        "purpose": "Automatically open a support ticket when the chatbot cannot help.",
        "expected_input": "user_id, question, conversation_summary",
        "expected_output": "ticket_id",
        "status": "Future integration",
    },
    {
        "name": "Open the relevant help page",
        "purpose": "Redirect the user directly to the relevant help center page.",
        "expected_input": "topic_or_source_id",
        "expected_output": "help_center_url",
        "status": "Future integration",
    },
]

# Geriye dönük uyumluluk için TR sabitler eski isimleriyle de dışa açık
# kalır (mevcut import eden kod varsa kırılmasın).
ACTIVE_SKILLS = _ACTIVE_SKILLS_TR
FUTURE_PLUGINS = _FUTURE_PLUGINS_TR

_SIMULATED_ACTIVITY_STATUSES_TR: Dict[str, str] = {
    "A01": "tamamlandı",
    "A02": "devam ediyor",
    "A09": "tamamlandı",
}

_SIMULATED_ACTIVITY_STATUSES_EN: Dict[str, str] = {
    "A01": "completed",
    "A02": "in progress",
    "A09": "completed",
}

SIMULATION_DISCLAIMER = "Simülasyon — gerçek Mobixa verisi değildir"
SIMULATION_DISCLAIMER_EN = "Simulation — not real Mobixa data"


def get_active_skills(language: str = "tr") -> List[str]:
    return _ACTIVE_SKILLS_EN if language == "en" else _ACTIVE_SKILLS_TR


def get_future_plugins(language: str = "tr") -> List[Dict[str, str]]:
    return _FUTURE_PLUGINS_EN if language == "en" else _FUTURE_PLUGINS_TR


def get_activity_status(activity_id: str, language: str = "tr") -> Dict[str, str]:
    """Sabit örnek veri döndüren, gerçek bir backend'e bağlı OLMAYAN simüle edilmiş eklenti.

    Hiçbir modelin bu sonucu uydurmasına izin verilmez; bu fonksiyon yalnızca
    Python tarafında sabit örnek veriyle çağrılır.
    """
    statuses = _SIMULATED_ACTIVITY_STATUSES_EN if language == "en" else _SIMULATED_ACTIVITY_STATUSES_TR
    unknown_label = "unknown" if language == "en" else "bilinmiyor"
    disclaimer = SIMULATION_DISCLAIMER_EN if language == "en" else SIMULATION_DISCLAIMER
    return {
        "activity_id": activity_id,
        "status": statuses.get(activity_id, unknown_label),
        "disclaimer": disclaimer,
    }
