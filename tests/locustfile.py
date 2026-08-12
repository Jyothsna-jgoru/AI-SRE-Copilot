from locust import HttpUser, between, task


class APIUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        response = self.client.post(
            "/auth/login",
            json={"email": "viewer@local.dev", "password": "viewer123"},
        )
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    @task(4)
    def list_incidents(self):
        self.client.get("/incidents", headers=self.headers)

    @task(1)
    def health(self):
        self.client.get("/health")

