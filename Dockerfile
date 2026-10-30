FROM node:26.12.0-trixie-slim AS ui
WORKDIR /project/frontend
RUN npm install --global @yarnpkg/cli-dist@4.18.1
COPY frontend/package.json frontend/yarn.lock frontend/.yarnrc.yml ./
RUN yarn install --immutable
COPY frontend ./
RUN yarn build

FROM python:3.15.0-slim
WORKDIR /project
COPY pyproject.toml README.md BACKEND.md ./
COPY requirements.lock ./
COPY src ./src
COPY packages/rag-evalkit ./packages/rag-evalkit
RUN pip install --no-deps -r requirements.lock && pip install --no-deps . ./packages/rag-evalkit
COPY --from=ui /project/frontend/dist ./frontend/dist
RUN groupadd --system --gid 10001 qa-workbench \
    && useradd --system --uid 10001 --gid qa-workbench --no-create-home qa-workbench \
    && mkdir -p /data/qa-workbench \
    && chown qa-workbench:qa-workbench /data/qa-workbench
EXPOSE 8765
USER 10001:10001
CMD ["qa-workbench", "--host", "0.0.0.0", "--token-env", "QA_WORKBENCH_TOKEN", "--frontend-dir", "frontend/dist", "--archive-root", "/data/qa-workbench"]
