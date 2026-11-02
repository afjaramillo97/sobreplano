# Lambda image for the daily scraper (SPEC 05). Build for arm64:
#   docker build --platform linux/arm64 --provenance=false -t sobreplano-scraper .

# Stage 1: turn uv.lock into a hashed requirements file, runtime dependencies only.
FROM ghcr.io/astral-sh/uv:0.13.4 AS uv
FROM public.ecr.aws/lambda/python:3.13 AS requirements
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock /build/
# --no-emit-project: the package itself is copied as source below, not installed.
RUN cd /build && uv export --frozen --no-dev --no-emit-project -o requirements.txt

# Stage 2: the Lambda image, without uv.
FROM public.ecr.aws/lambda/python:3.13
COPY --from=requirements /build/requirements.txt /tmp/requirements.txt
# --require-hashes is implied by the hashes uv writes: every wheel must match the lock.
RUN pip install --no-cache-dir -r /tmp/requirements.txt --target "${LAMBDA_TASK_ROOT}" \
    && rm /tmp/requirements.txt
COPY src/sobreplano "${LAMBDA_TASK_ROOT}/sobreplano"
CMD ["sobreplano.interface.lambda_handler.handler"]
