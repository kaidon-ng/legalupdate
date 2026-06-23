FROM apify/actor-python-playwright-chrome:latest

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

ENV CI=true
ENV OPENAI_MODEL=gpt-5.4

CMD ["python", "actor_main.py"]
