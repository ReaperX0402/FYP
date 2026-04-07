from pathlib import Path

from src.ai_model.angle_classifier import AngleClassifier


def main() -> None:
    model_path = Path("src/ai_model/best_angle_classifier_model_2.pt")
    image_dir = Path("data/test_batch")

    classifier = AngleClassifier(model_path)

    for image_path in image_dir.glob("*.*"):
        result = classifier.predict(image_path)
        print(image_path.name, "->", result)


if __name__ == "__main__":
    main()