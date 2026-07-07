class GoogleDriveConnector:
    connector_type = "google_drive"

    def sync(self):
        return {"connector_type": self.connector_type, "synced": 0, "status": "not_implemented"}

