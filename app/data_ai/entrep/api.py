from fastapi import FastAPI
import joblib
import numpy as np

# créer application API
app = FastAPI()

# charger le modèle ML
model = joblib.load("irrigation_model.pkl")

# route de test
@app.get("/")
def home():
    return {"message": "Smart Irrigation API is running"}

# route prediction
@app.post("/predict")
def predict(data: dict):

    soil_humidity = data["soil_humidity"]
    temperature = data["temperature"]

    # préparer données pour le modèle
    X = np.array([[soil_humidity, temperature]])

    prediction = model.predict(X)[0]

    if prediction == 1:
        result = "Irrigation needed"
    else:
        result = "No irrigation needed"

    return {
        "soil_humidity": soil_humidity,
        "temperature": temperature,
        "prediction": int(prediction),
        "decision": result
    }