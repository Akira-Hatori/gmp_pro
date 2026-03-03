/**
 * @file asio_tcp_helper.hpp
 * @brief 基于 ASIO 的 TCP 通信辅助类，用于 Simulink S-Function 锁步通信
 * @version 1.1
 * @date 2026-03-02
 *
 * @note 核心特性：
 *   1. 启用 TCP_NODELAY 禁用 Nagle 算法，实现极致低延迟
 *   2. 使用 asio::read 精确读取，彻底解决 TCP 粘包/拆包问题
 *   3. 完善的异常处理，防止宿主进程崩溃
 *   4. Client 端连接失败自动重试
 */

#pragma once

#include <algorithm>
#include <chrono>
#include <exception>
#include <fstream>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>

// ASIO 平台适配
#if !defined __linux__
#include <SDKDDKVer.h>
#endif

#define ASIO_STANDALONE
#include <asio.hpp>

#if !defined __linux__
#include <Windows.h>
#endif

// 【修复】超时宏必须在使用之前定义
#ifndef GMP_ASIO_TCP_LINK_TIMEOUT
#define GMP_ASIO_TCP_LINK_TIMEOUT 5000 // 默认 5 秒超时
#endif

// Client 连接重试配置
#ifndef GMP_TCP_CONNECT_RETRY_COUNT
#define GMP_TCP_CONNECT_RETRY_COUNT 10 // 最大重试次数
#endif

#ifndef GMP_TCP_CONNECT_RETRY_INTERVAL_MS
#define GMP_TCP_CONNECT_RETRY_INTERVAL_MS 1000 // 重试间隔（毫秒）
#endif

using json = nlohmann::json;
using namespace asio;
using tcp = ip::tcp;

class asio_tcp_helper
{
  public:
    // IO Context
    io_context data_context;
    io_context cmd_context;

    // 数据通道 Socket
    tcp::socket data_socket;

    // 命令通道 Socket
    tcp::socket cmd_socket;

#ifdef ASIO_TCP_HELPER_SERVER_MODE
    // Server 模式下使用 acceptor
    std::unique_ptr<tcp::acceptor> data_acceptor;
    std::unique_ptr<tcp::acceptor> cmd_acceptor;
#endif

    // 端口配置（保持与 UDP 版语义一致）
    uint32_t recv_port, trans_port;
    uint32_t cmd_recv_port, cmd_trans_port;
    std::string target_ip;

    // 命令缓冲区与状态标志
    std::string cmd_recv_buf;
    uint32_t stop_cmd_received;
    uint32_t start_cmd_received;
    uint32_t recv_counter;
    uint32_t tran_counter;

    // 连接状态
    bool is_connected;

  public:
    /**
     * @brief 构造函数
     * @param ip_addr   远程目标 IP 地址
     * @param r_port    接收端口（与 UDP 版语义一致）
     * @param t_port    发送端口（与 UDP 版语义一致）
     * @param cr_port   命令接收端口
     * @param ct_port   命令发送端口
     *
     * @note 端口映射逻辑与 UDP 版保持一致：
     *       Server 模式：监听 t_port（数据）和 ct_port（命令）
     *       Client 模式：连接到远程 t_port（数据）和 ct_port（命令）
     */
    asio_tcp_helper(const std::string ip_addr, uint32_t r_port, uint32_t t_port, uint32_t cr_port, uint32_t ct_port)
        : data_socket(data_context), cmd_socket(cmd_context), recv_port(r_port), trans_port(t_port),
          cmd_recv_port(cr_port), cmd_trans_port(ct_port), target_ip(ip_addr), cmd_recv_buf(1024, '\0'),
          stop_cmd_received(0), start_cmd_received(0), recv_counter(0), tran_counter(0), is_connected(false)
    {
    }

    ~asio_tcp_helper()
    {
        release_connect();
    }

    // 禁止拷贝
    asio_tcp_helper(const asio_tcp_helper&) = delete;
    asio_tcp_helper& operator=(const asio_tcp_helper&) = delete;

    /**
     * @brief 建立 TCP 连接
     *
     * @note
     *  端口映射关系（与 UDP 版保持一致）：
     *
     *  Server 模式（控制器 C++ 程序）:
     *    - 数据通道：监听 trans_port (t_port)，接受来自 Simulink 的连接
     *    - 命令通道：监听 cmd_trans_port (ct_port)，接受来自 Simulink 的连接
     *    - 连接建立后，数据通道 socket 既用于收也用于发
     *
     *  Client 模式（Simulink S-Function）:
     *    - 数据通道：连接到远程 trans_port (t_port)
     *    - 命令通道：连接到远程 cmd_trans_port (ct_port)
     *    - 连接失败时自动重试
     */
    void connect_to_target()
    {
        try
        {
#ifdef ASIO_TCP_HELPER_SERVER_MODE
            // ===== Server 模式：创建 Acceptor 并等待客户端连接 =====

            // 数据通道 Acceptor：监听 trans_port（与 UDP 版 Server bind t_port 一致）
            data_acceptor =
                std::make_unique<tcp::acceptor>(data_context, tcp::endpoint(tcp::v4(), static_cast<ip::port_type>(trans_port)));
            data_acceptor->set_option(tcp::acceptor::reuse_address(true));

            std::cout << "[ASIO-TCP] Server waiting for data connection on port " << trans_port << "..." << std::endl;

            // 阻塞等待数据通道连接
            data_acceptor->accept(data_socket);

            // 【关键】立即启用 TCP_NODELAY
            enable_no_delay(data_socket);

            std::cout << "[ASIO-TCP] Data channel connected from: "
                      << data_socket.remote_endpoint().address().to_string() << std::endl;

            // 命令通道 Acceptor：监听 cmd_trans_port
            cmd_acceptor = std::make_unique<tcp::acceptor>(
                cmd_context, tcp::endpoint(tcp::v4(), static_cast<ip::port_type>(cmd_trans_port)));
            cmd_acceptor->set_option(tcp::acceptor::reuse_address(true));

            std::cout << "[ASIO-TCP] Server waiting for command connection on port " << cmd_trans_port << "..."
                      << std::endl;

            // 阻塞等待命令通道连接
            cmd_acceptor->accept(cmd_socket);

            // 【关键】立即启用 TCP_NODELAY
            enable_no_delay(cmd_socket);

            std::cout << "[ASIO-TCP] Command channel connected from: "
                      << cmd_socket.remote_endpoint().address().to_string() << std::endl;

#else
            // ===== Client 模式：主动发起连接（带重试） =====

            // 数据通道：连接到远程 trans_port（与 UDP 版 Client 连接 t_port 一致）
            tcp::endpoint data_target(ip::make_address(target_ip), static_cast<ip::port_type>(trans_port));

            std::cout << "[ASIO-TCP] Client connecting to " << target_ip << ":" << trans_port << "..." << std::endl;

            connect_with_retry(data_socket, data_target, "Data");

            // 【关键】立即启用 TCP_NODELAY
            enable_no_delay(data_socket);

            std::cout << "[ASIO-TCP] Data channel established." << std::endl;

            // 命令通道：连接到远程 cmd_trans_port
            tcp::endpoint cmd_target(ip::make_address(target_ip), static_cast<ip::port_type>(cmd_trans_port));

            std::cout << "[ASIO-TCP] Client connecting command channel to " << target_ip << ":" << cmd_trans_port
                      << "..." << std::endl;

            connect_with_retry(cmd_socket, cmd_target, "Command");

            // 【关键】立即启用 TCP_NODELAY
            enable_no_delay(cmd_socket);

            std::cout << "[ASIO-TCP] Command channel established." << std::endl;

#endif // ASIO_TCP_HELPER_SERVER_MODE

            is_connected = true;
            std::cout << "[ASIO-TCP] All channels ready. TCP_NODELAY enabled." << std::endl;
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] Connection Error: " << e.what() << std::endl;
            cleanup_sockets();
            is_connected = false;
        }
    }

    /**
     * @brief 释放所有连接资源
     */
    void release_connect()
    {
        try
        {
            // 停止 IO context（会取消所有异步操作）
            cmd_context.stop();
            data_context.stop();

            cleanup_sockets();

#ifdef ASIO_TCP_HELPER_SERVER_MODE
            // 关闭 Acceptor
            if (data_acceptor && data_acceptor->is_open())
            {
                data_acceptor->close();
            }
            if (cmd_acceptor && cmd_acceptor->is_open())
            {
                cmd_acceptor->close();
            }
#endif
            is_connected = false;
            std::cout << "[ASIO-TCP] Connection released." << std::endl;
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] Release Error: " << e.what() << std::endl;
        }
    }

    /**
     * @brief 发送命令消息
     * @param msg 消息指针
     * @param len 消息长度
     */
    void send_cmd(const char* msg, uint32_t len)
    {
        try
        {
            if (!cmd_socket.is_open())
            {
                std::cerr << "[ASIO-TCP] Command socket not open." << std::endl;
                return;
            }

            // 使用 asio::write 确保完整发送
            asio::write(cmd_socket, buffer(msg, len));
            tran_counter += len;
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] Send Command Error: " << e.what() << std::endl;
            handle_socket_error(cmd_socket);
        }
    }

    /**
     * @brief 发送数据消息
     * @param msg 消息指针
     * @param len 消息长度（字节）
     * @note 使用 asio::write 确保完整发送所有字节
     *       数据通道不加锁以保证最低延迟（锁步模型下不存在并发写入）
     */
    void send_msg(const char* msg, uint32_t len)
    {
        try
        {
            if (!data_socket.is_open())
            {
                std::cerr << "[ASIO-TCP] Data socket not open." << std::endl;
                return;
            }

            // 【关键】使用 asio::write 确保完整发送，避免部分写入
            asio::write(data_socket, buffer(msg, len));
            tran_counter += len;
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] Send Data Error: " << e.what() << std::endl;
            handle_socket_error(data_socket);
        }
    }

    /**
     * @brief 接收数据消息（精确读取）
     * @param msg 接收缓冲区指针
     * @param len 期望接收的精确字节数
     * @return 0 成功，1 失败
     *
     * @note 【核心防粘包机制】
     *       使用 asio::read() 强制精确读取 len 字节。
     *       此函数会阻塞直到收到完整的 len 字节数据，
     *       彻底解决 TCP 流式传输的粘包/拆包问题。
     *       数据通道不加锁以保证最低延迟（锁步模型下不存在并发读取）
     */
    int recv_msg(char* msg, uint32_t len)
    {
        try
        {
            if (!data_socket.is_open())
            {
                std::cerr << "[ASIO-TCP] Data socket not open for receive." << std::endl;
                return 1;
            }

            // 【关键】使用 asio::read 精确读取 len 字节
            // 禁止使用 read_some / recv，它们不保证读取完整数据
            std::size_t bytes_read = asio::read(data_socket, buffer(msg, len));

            recv_counter += static_cast<uint32_t>(bytes_read);
            return 0;
        }
        catch (const asio::system_error& e)
        {
            // 区分 EOF（对端正常关闭）与其他错误
            if (e.code() == asio::error::eof)
            {
                std::cerr << "[ASIO-TCP] Connection closed by peer (EOF)." << std::endl;
            }
            else
            {
                std::cerr << "[ASIO-TCP] Recv Error: " << e.what() << " (code: " << e.code() << ")" << std::endl;
            }
            handle_socket_error(data_socket);
            return 1;
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] Recv Error (generic): " << e.what() << std::endl;
            handle_socket_error(data_socket);
            return 1;
        }
    }

    /**
     * @brief 异步监听命令通道（Server 模式专用）
     * @note 【修复】使用单个持久线程运行 io_context，避免线程泄漏
     */
    void server_ack_cmd()
    {
        try
        {
            if (!cmd_socket.is_open())
            {
                std::cerr << "[ASIO-TCP] Command socket not available for async receive." << std::endl;
                return;
            }

            // 先投递一个异步读取操作
            post_async_cmd_read();

            // 使用 detached 线程运行（与 UDP 版模式一致，避免 ABI 兼容性问题）
            std::thread([this]() {
                try
                {
                    io_context::work work(cmd_context);
                    cmd_context.run();
                }
                catch (const std::exception& e)
                {
                    std::cerr << "[ASIO-TCP] Command thread error: " << e.what() << std::endl;
                }
            }).detach();
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] server_ack_cmd Error: " << e.what() << std::endl;
        }
    }

    /**
     * @brief 设置接收超时
     * @note 保持与 UDP 版类似的超时策略：
     *       Server 模式下建立连接后放宽超时
     *       Client 模式下建立连接后启用超时
     */
    void set_overtime()
    {
#if !defined(DISABLE_ASIO_HELPER_TIMEOUT_OPTION)

        uint32_t timeout_ms = GMP_ASIO_TCP_LINK_TIMEOUT;

#ifdef ASIO_TCP_HELPER_SERVER_MODE
        // Server 模式：连接建立后放宽超时（与 UDP 版逻辑一致）
        if (this->recv_counter > 100)
        {
            timeout_ms = 2000000; // ~33 分钟
        }
#else
        // Client 模式：连接建立后启用超时
        if (this->recv_counter <= 100)
        {
            return; // 初始阶段不设超时
        }
#endif

#if defined __linux__
        struct timeval tv;
        tv.tv_sec = timeout_ms / 1000;
        tv.tv_usec = (timeout_ms % 1000) * 1000;

        if (setsockopt(data_socket.native_handle(), SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) < 0)
        {
            std::cerr << "[ASIO-TCP] setsockopt SO_RCVTIMEO failed." << std::endl;
        }
#else // Windows
        DWORD dw_timeout = static_cast<DWORD>(timeout_ms);
        if (setsockopt(data_socket.native_handle(), SOL_SOCKET, SO_RCVTIMEO,
                       reinterpret_cast<const char*>(&dw_timeout), sizeof(dw_timeout)) < 0)
        {
            std::cerr << "[ASIO-TCP] setsockopt SO_RCVTIMEO failed." << std::endl;
        }
#endif

#endif // DISABLE_ASIO_HELPER_TIMEOUT_OPTION
    }

    /**
     * @brief 检查连接状态
     */
    bool is_link_established() const
    {
        return is_connected && data_socket.is_open();
    }

    /**
     * @brief 从 JSON 配置文件解析并创建实例
     * @param config_file JSON 配置文件路径
     * @return 成功返回实例指针，失败返回 nullptr
     */
    static asio_tcp_helper* parse_network_config(const std::string& config_file)
    {
        std::ifstream f(config_file);

        if (!f.is_open())
        {
            std::cerr << "[ASIO-TCP] Cannot find network config file: " << config_file << std::endl;
            return nullptr;
        }

        json config;

        try
        {
            config = json::parse(f);
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] JSON parse error in " << config_file << ": " << e.what() << std::endl;
            return nullptr;
        }

        try
        {
            std::string target_addr = config["target_address"];
            uint32_t recv_port = config["receive_port"];
            uint32_t trans_port = config["transmit_port"];
            uint32_t cmd_recv_port = config["command_recv_port"];
            uint32_t cmd_trans_port = config["command_trans_port"];

            // 注意：参数顺序与 UDP 版 parse_network_config 保持一致
            return new asio_tcp_helper(target_addr, trans_port, recv_port, cmd_trans_port, cmd_recv_port);
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] Config parse error: " << e.what() << std::endl;
            return nullptr;
        }
    }

  private:
    /**
     * @brief 启用 TCP_NODELAY 选项
     * @param sock 目标 socket
     */
    void enable_no_delay(tcp::socket& sock)
    {
        try
        {
            sock.set_option(tcp::no_delay(true));
        }
        catch (const std::exception& e)
        {
            std::cerr << "[ASIO-TCP] Failed to set TCP_NODELAY: " << e.what() << std::endl;
        }
    }

    /**
     * @brief Client 端连接重试逻辑
     * @param sock 目标 socket
     * @param endpoint 连接目标端点
     * @param channel_name 通道名称（用于日志）
     * @throw 超过最大重试次数后抛出异常
     */
    void connect_with_retry(tcp::socket& sock, const tcp::endpoint& endpoint, const std::string& channel_name)
    {
        std::error_code ec;

        for (int attempt = 1; attempt <= GMP_TCP_CONNECT_RETRY_COUNT; ++attempt)
        {
            ec.clear();

            if (!sock.is_open())
            {
                sock.open(tcp::v4(), ec);
                if (ec)
                {
                    std::cerr << "[ASIO-TCP] " << channel_name << " socket open failed: " << ec.message() << std::endl;
                    continue;
                }
            }

            sock.connect(endpoint, ec);

            if (!ec)
            {
                // 连接成功
                return;
            }

            std::cerr << "[ASIO-TCP] " << channel_name << " connect attempt " << attempt << "/"
                      << GMP_TCP_CONNECT_RETRY_COUNT << " failed: " << ec.message() << std::endl;

            // 关闭 socket 以便下次重试
            if (sock.is_open())
            {
                std::error_code close_ec;
                sock.close(close_ec);
            }

            if (attempt < GMP_TCP_CONNECT_RETRY_COUNT)
            {
                std::cout << "[ASIO-TCP] Retrying in " << GMP_TCP_CONNECT_RETRY_INTERVAL_MS << "ms..." << std::endl;
                std::this_thread::sleep_for(std::chrono::milliseconds(GMP_TCP_CONNECT_RETRY_INTERVAL_MS));
            }
        }

        // 超过重试次数，抛出异常
        throw std::runtime_error("[ASIO-TCP] " + channel_name + " connection failed after " +
                                 std::to_string(GMP_TCP_CONNECT_RETRY_COUNT) + " attempts. Last error: " +
                                 ec.message());
    }

    /**
     * @brief 投递异步命令读取
     */
    void post_async_cmd_read()
    {
        if (!cmd_socket.is_open())
            return;

        cmd_socket.async_read_some(asio::buffer(cmd_recv_buf), [this](std::error_code ec, std::size_t bytes_recvd) {
            if (!ec && bytes_recvd > 0)
            {
                if (cmd_recv_buf.find("Stop") != std::string::npos)
                {
                    stop_cmd_received = 1;
                    std::cout << "[ASIO-TCP] Stop command received." << std::endl;
                    this->release_connect();
                    return;
                }
                else if (cmd_recv_buf.find("Start") != std::string::npos)
                {
                    start_cmd_received = 1;
                    std::cout << "[ASIO-TCP] Start command received." << std::endl;
                }
                std::fill(cmd_recv_buf.begin(), cmd_recv_buf.end(), '\0');
            }
            else if (ec)
            {
                if (ec == asio::error::eof || ec == asio::error::connection_reset)
                {
                    std::cerr << "[ASIO-TCP] Command channel disconnected: " << ec.message() << std::endl;
                    stop_cmd_received = 1;
                }
                else if (ec != asio::error::operation_aborted)
                {
                    std::cerr << "[ASIO-TCP] Async cmd receive error: " << ec.message() << std::endl;
                }
                return;
            }

            // 继续监听下一条命令
            if (!cmd_context.stopped())
                post_async_cmd_read();
        });
    }

    /**
     * @brief 清理所有 Socket 资源
     */
    void cleanup_sockets()
    {
        auto safe_close = [](tcp::socket& sock) {
            try
            {
                if (sock.is_open())
                {
                    std::error_code ec;
                    sock.shutdown(tcp::socket::shutdown_both, ec);
                    sock.close(ec);
                }
            }
            catch (...)
            {
            }
        };

        safe_close(data_socket);
        safe_close(cmd_socket);
    }

    /**
     * @brief 处理 Socket 错误
     * @param sock 发生错误的 socket
     */
    void handle_socket_error(tcp::socket& sock)
    {
        try
        {
            if (sock.is_open())
            {
                std::error_code ec;
                sock.shutdown(tcp::socket::shutdown_both, ec);
                sock.close(ec);
            }
            is_connected = false;
        }
        catch (...)
        {
        }
    }
};