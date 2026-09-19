FROM public.ecr.aws/lambda/python:3.12

# Amazon Linux 2023 base (glibc 2.34): modern manylinux_2_28 wheels for
# scipy / lightgbm / scikit-learn install directly, no compiler needed.
# lightgbm needs libgomp (OpenMP) at runtime. dnf here is microdnf.
# Retry loops keep the build alive on a slow / flaky network.
RUN for i in 1 2 3 4 5; do dnf install -y libgomp && break || { echo "dnf attempt $i failed, retrying"; sleep 5; }; done

COPY requirements.txt .
# --only-binary: never compile from source (no compiler in this image);
# fail fast with a readable error instead.
RUN for i in 1 2 3; do pip install --no-cache-dir --only-binary=:all: --default-timeout=120 --retries 10 -r requirements.txt && break || { echo "pip attempt $i failed, retrying"; sleep 5; }; done \
    && python -c "import pandas, numpy, sklearn, lightgbm, joblib, scipy; print('deps import OK')"

COPY lib ${LAMBDA_TASK_ROOT}/lib
COPY models ${LAMBDA_TASK_ROOT}/models
COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
