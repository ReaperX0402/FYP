from pathlib import Path

from src.ai_model.angle_classifier import AngleClassifier
from src.ai_model.angle_suggester import suggest_next_angles


def main() -> None:
    model_path = Path("src/ai_model/best_angle_classifier.pt")
    image_path = Path("data/test.jpg")  

    classifier = AngleClassifier(model_path)
    result = classifier.predict(image_path)

    print("Prediction:", result)

    captured = {
        result["object"]: {result["angle"]}
    }
    print("Suggested next angles:", suggest_next_angles(result["object"], captured))


if __name__ == "__main__":
    main()