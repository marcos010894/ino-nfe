import httpx

client_id = "4RytzXjzwdlIWhUaeAi0"
client_secret = "vZVz6djCDRr0jGblXM3JENPRC560nU0F"
token_url = "https://auth.acbr.api.br/realms/ACBrAPI/protocol/openid-connect/token"

data = {
    "grant_type": "client_credentials",
    "client_id": client_id,
    "client_secret": client_secret
}

try:
    response = httpx.post(token_url, data=data)
    print("STATUS CODE:", response.status_code)
    print("RESPONSE:", response.json())
except Exception as e:
    print("ERROR:", e)
