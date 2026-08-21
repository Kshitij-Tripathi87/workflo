from workflo.ui.pages.base_page import BasePage


class LoginPage(BasePage):
    URL_PATH = "/login"

    def navigate_to(self, base_url: str):
        self.navigate(f"{base_url}{self.URL_PATH}")

    def fill_email(self, email: str):
        self.wait_for_data_testid("email-input")
        self.fill_testid("email-input", email)

    def fill_password(self, password: str):
        self.fill_testid("password-input", password)

    def click_login(self):
        self.click_testid("login-btn")

    def login_as(self, base_url: str, email: str, password: str):
        self.navigate_to(base_url)
        self.fill_email(email)
        self.fill_password(password)
        self.click_login()
        self.page.wait_for_load_state("networkidle", timeout=15000)
        self.page.wait_for_url("**/dashboard**", timeout=15000)
