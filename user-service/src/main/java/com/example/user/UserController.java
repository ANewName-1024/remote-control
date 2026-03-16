package com.example.user;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/user")
public class UserController {

    @Autowired
    private UserRepository userRepository;

    @GetMapping("/list")
    public List<User> list() {
        return userRepository.findAll();
    }

    @PostMapping("/add")
    public User add(@RequestParam String username, @RequestParam String email) {
        User user = new User(username, email);
        return userRepository.save(user);
    }

    @GetMapping("/health")
    public String health() {
        return "OK";
    }
}
