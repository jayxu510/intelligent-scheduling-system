# 阶段 1: 使用 Node 打包 React/Vite 前端
FROM node:18-alpine as build-stage
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# 阶段 2: 使用 Nginx 托管静态文件
FROM nginx:alpine as production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
# 引入自定义的 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]