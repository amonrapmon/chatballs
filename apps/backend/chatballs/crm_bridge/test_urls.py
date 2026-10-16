from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase

from chatballs.crm_bridge.search_urls import build_client_search_url, normalize_phone


class CRMSearchLinkTests(SimpleTestCase):
    def test_phone_normalization_does_not_guess_country(self):
        self.assertEqual(normalize_phone("+7 (916) 254-52-43"), "79162545243")
        self.assertEqual(normalize_phone("79162545243"), "79162545243")
        self.assertEqual(normalize_phone("8 (916) 254-52-43"), "89162545243")

    def test_unusable_phone_is_rejected(self):
        for number in (None, "", "abc79162545243", "0000000", "123", "9" * 16, "a@b.com", "٩١٦٢٥٤٥٢٤٣"):
            with self.subTest(number=number):
                self.assertIsNone(normalize_phone(number))

    def test_dikidi_link(self):
        self.assertEqual(
            build_client_search_url("DIKIDI", "515337", "+7 980 356-57-58"),
            "https://dikidi.net/ru/owner/clients/?company=515337&filter=username&query=79803565758",
        )

    def test_yclients_link_preserves_three_filters(self):
        link = build_client_search_url("YCLIENTS", "688638", "+7 916 254-52-43")
        self.assertIsNotNone(link)
        result = urlsplit(link)
        self.assertEqual(result.path, "/clients/688638/base")
        self.assertEqual(parse_qs(result.query), {
            "filters[0][operation]": ["OR"],
            "filters[1][type]": ["quick_search"],
            "filters[1][state][value]": ["79162545243"],
        })
        self.assertIn("filters%5B0%5D%5Boperation%5D=OR", link)

    def test_reject_bad_company_and_provider(self):
        for provider, company in (
            ("NONE", "123"), ("YCLIENTS", "123evil"), ("DIKIDI", "https://example.com")
        ):
            with self.subTest(provider=provider, company=company):
                self.assertIsNone(build_client_search_url(provider, company, "79162545243"))
