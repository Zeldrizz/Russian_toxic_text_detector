# -*- coding: utf-8 -*-
"""russian_toxic_detection.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1lvSr1a5B75OjNh5PZ7tTcd37a5KVXs4b

## **Dataset parsing - Парсим датасет**
"""

!pip install emoji

import re
import emoji
from tqdm import tqdm

def remove_emoji(text):
    return emoji.demojize(text)

def parse_dataset(file_path):
    labels = []
    comments = []
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
        for line in tqdm(lines, desc="Parsing dataset"):
            match = re.match(r'((?:__label__[A-Z_]+,?)+)\s(.+)', line)
            if match:
                label_str = match.group(1)
                comment = match.group(2)
                comment = remove_emoji(comment)
                label_list = label_str.split(',')
                labels.append(label_list)
                comments.append(comment)
    return labels, comments

file_path = 'dataset.txt'
labels, comments = parse_dataset(file_path)

for i in range(30):
    print(labels[i], comments[i])

"""## **Dataset processing - Обработка датасета**"""

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from transformers import BertTokenizer
import torch
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

from sklearn.preprocessing import MultiLabelBinarizer

mlb = MultiLabelBinarizer()
binary_labels = mlb.fit_transform(labels)

comments_train, comments_temp, labels_train, labels_temp = train_test_split(comments, binary_labels, test_size=0.3, random_state=42)
comments_val, comments_test, labels_val, labels_test = train_test_split(comments_temp, labels_temp, test_size=0.5, random_state=42)

print(f'Train size: {len(comments_train)}')
print(f'Validation size: {len(comments_val)}')
print(f'Test size: {len(comments_test)}')

tokenizer = BertTokenizer.from_pretrained('bert-base-multilingual-cased')

def encode_data(tokenizer, texts, max_length):
    input_ids = []
    attention_masks = []

    for text in tqdm(texts, desc="Tokenizing"):
        encoded_dict = tokenizer.encode_plus(
            text,
            add_special_tokens=True,
            padding='max_length',
            max_length=max_length,
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt',
        )
        input_ids.append(encoded_dict['input_ids'])
        attention_masks.append(encoded_dict['attention_mask'])

    return torch.cat(input_ids, dim=0), torch.cat(attention_masks, dim=0)

max_length = 32

train_inputs, train_masks = encode_data(tokenizer, comments_train, max_length)
val_inputs, val_masks = encode_data(tokenizer, comments_val, max_length)
test_inputs, test_masks = encode_data(tokenizer, comments_test, max_length)

train_labels = torch.tensor(labels_train).float()
val_labels = torch.tensor(labels_val).float()
test_labels = torch.tensor(labels_test).float()

train_dataset = TensorDataset(train_inputs, train_masks, train_labels)
val_dataset = TensorDataset(val_inputs, val_masks, val_labels)
test_dataset = TensorDataset(test_inputs, test_masks, test_labels)

train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=16)
test_loader = DataLoader(test_dataset, batch_size=16)

"""## **Neural network initialization - Инициализация нейронной сети**"""

from transformers import BertModel
import torch.nn as nn
import torch.optim as optim

class RussianTextClassifier(nn.Module):
    def __init__(self, num_labels):
        super(RussianTextClassifier, self).__init__()
        self.bert = BertModel.from_pretrained('bert-base-multilingual-cased')
        self.dropout = nn.Dropout(0.3)
        self.classifier = nn.Linear(self.bert.config.hidden_size, num_labels)

    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        pooled_output = outputs[1]
        pooled_output = self.dropout(pooled_output)
        logits = self.classifier(pooled_output)
        return logits

device = 'cuda' if torch.cuda.is_available() else 'cpu'
device

num_labels = len(mlb.classes_) # 4
learning_rate = 1e-5
num_epochs = 3 # и одной эпохи достаточно, очень высокий accuracy

model = RussianTextClassifier(num_labels).to(device)
criterion = nn.BCEWithLogitsLoss()
optimizer = optim.AdamW(model.parameters(), lr=learning_rate)

"""## **Model training - Тренировка модели**"""

for epoch in range(num_epochs):
    model.train()
    total_loss = 0
    progress_bar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{num_epochs}")

    for batch in progress_bar:
        b_input_ids, b_input_mask, b_labels = batch
        b_input_ids, b_input_mask, b_labels = b_input_ids.to(device), b_input_mask.to(device), b_labels.to(device)

        optimizer.zero_grad()
        output = model(b_input_ids, b_input_mask)
        loss = criterion(output, b_labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        progress_bar.set_postfix(loss=total_loss/len(train_loader))

    print(f'Epoch {epoch+1}/{num_epochs}, Loss: {total_loss/len(train_loader)}')

    model.eval()
    correct, total = 0, 0
    val_loss = 0
    progress_bar = tqdm(val_loader, desc=f"Validation Epoch {epoch+1}/{num_epochs}")

    with torch.no_grad():
        for batch in progress_bar:
            b_input_ids, b_input_mask, b_labels = batch
            b_input_ids, b_input_mask, b_labels = b_input_ids.to(device), b_input_mask.to(device), b_labels.to(device)
            output = model(b_input_ids, b_input_mask)
            loss = criterion(output, b_labels)
            val_loss += loss.item()

            predictions = torch.sigmoid(output) > 0.5
            correct += (predictions == b_labels).sum().item()
            total += b_labels.numel()
            progress_bar.set_postfix(accuracy=100 * correct / total, val_loss=val_loss/len(val_loader))

    print(f'\nValidation Accuracy: {100 * correct / total}%, Validation Loss: {val_loss/len(val_loader)}')

model.eval()
correct, total = 0, 0
test_loss = 0
progress_bar = tqdm(test_loader, desc="Testing")

with torch.no_grad():
    for batch in progress_bar:
        b_input_ids, b_input_mask, b_labels = batch
        b_input_ids, b_input_mask, b_labels = b_input_ids.to(device), b_input_mask.to(device), b_labels.to(device)
        output = model(b_input_ids, b_input_mask)
        loss = criterion(output, b_labels)
        test_loss += loss.item()
        predictions = torch.sigmoid(output) > 0.5
        correct += (predictions == b_labels).sum().item()
        total += b_labels.numel()
        progress_bar.set_postfix(accuracy=100 * correct / total, test_loss=test_loss/len(test_loader))

print(f'\nTest Accuracy: {100 * correct / total}%, Test Loss: {test_loss/len(test_loader)}')

"""## **Model using - Использование модели**"""

def predict_comment(comment):
    model.eval()
    with torch.no_grad():
        encoded_dict = tokenizer.encode_plus(
            comment,
            add_special_tokens=True,
            max_length=max_length,
            padding='max_length',
            return_attention_mask=True,
            return_tensors='pt',
        )
        input_id = encoded_dict['input_ids'].to(device)
        attention_mask = encoded_dict['attention_mask'].to(device)
        output = model(input_id, attention_mask)

        probabilities = torch.sigmoid(output).cpu().numpy()

    predicted_labels = (probabilities > 0.5).astype(int)

    return mlb.inverse_transform(predicted_labels)

def check(comment: str):
    predicted_labels = predict_comment(comment)
    result = "Вердикт нейросети RussianTextClassifier: "

    label_map = {
        "__label__NORMAL": "Норма",
        "__label__INSULT": "Оскорбление или нецензурная брань",
        "__label__THREAT": "Грозное преднамерение",
        "__label__OBSCENITY": "Вульгарность"
    }

    labels_text = [label_map[label] for label in predicted_labels[0] if label in label_map]

    if len(labels_text) > 1 and "Норма" in labels_text:
        labels_text.remove("Норма")

    result += ", ".join(labels_text)

    return result

example_comment = input("Входной текст: ")
check(example_comment)

"""### **Some examples (Warning: Contains obscene language) - Некоторые примеры (Предупреждение! Содержат нецензурную брань)**"""

example = "Ой, Васька, во дает, вот он идиот..."

print("Входной текст: ", example)
check(example)

example = "да, на бутылку насадить эту блядь"

print("Входной текст: ", example)
check(example)

example = "Сегодня был довольно жаркий день"

print("Входной текст: ", example)
check(example)

example = "Жара, июль, комары, пиво"

print("Входной текст: ", example)
check(example)

example = "На кол бы посадить твоего мужа"

print("Входной текст: ", example)
check(example)

example = "Мои людью убьют всю твою семью"

print("Входной текст: ", example)
check(example)

example = "вот бы ей присунуть прямо в поезде)"

print("Входной текст: ", example)
check(example)

example = "уххх какая сочная задница"

print("Входной текст: ", example)
check(example)

example = "опять эти дауны зумеры, опять херни натворили"

print("Входной текст: ", example)
check(example)

example = "иуда меченная,сука,повесить его мало."

print("Входной текст: ", example)
check(example)

example = "https://natali37.ru/product/11320 50 размер блузка агния 270 руб. 1 шт"

print("Входной текст: ", example)
check(example)

example = "тебя бы я так трахнулбе"

print("Входной текст: ", example)
check(example)