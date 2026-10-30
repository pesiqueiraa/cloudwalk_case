from helpdesk.config import Settings


def test_settings_defaults():
    settings = Settings(database_url="postgresql://x")
    assert settings.topic_inbound == "helpdesk.inbound"
    assert settings.topic_outbound == "helpdesk.outbound"
