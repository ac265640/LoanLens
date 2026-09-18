FROM public.ecr.aws/lambda/python:3.11

# lightgbm needs libgomp at runtime (OpenMP), not present in the base image by default
RUN dnf install -y libgomp && dnf clean all

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lib ${LAMBDA_TASK_ROOT}/lib
COPY models ${LAMBDA_TASK_ROOT}/models
COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
