import requests

def send_request(email, password):

    response = requests.post(
        "http://127.0.0.1:8000/login",
        json={
            "email": email,
            "password": password
        }
    )

    print(response.status_code)
    print(response.text)

    return response.text
