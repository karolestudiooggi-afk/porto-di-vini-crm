from sync.domani_client import DomaniClient


def test_raw_to_contact_extrai_campos_nativos_tags_e_user_fields():
    client = object.__new__(DomaniClient)
    contact = client.raw_to_contact(
        {
            "user_ns": "u1",
            "user_id": "social-1",
            "channel": "instagram",
            "name": "Ana",
            "opt_in_email": "true",
            "tags": [{"name": "vip"}, {"name": ""}],
            "user_fields": [
                {"name": "pontuacao", "value": "2", "var_type": "number"},
                {"name": "preferencias", "value": '["pizza"]', "var_type": "array"},
            ],
        }
    )

    assert contact.user_ns == "u1"
    assert contact.user_id == "social-1"
    assert contact.tags == ["vip"]
    assert contact.user_fields == {"pontuacao": 2, "preferencias": ["pizza"]}
