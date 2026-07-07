class NotionConnector:
    connector_type = "notion"

    def sync(self):
        return {"connector_type": self.connector_type, "synced": 0, "status": "not_implemented"}

