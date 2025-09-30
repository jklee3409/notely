package com.mycom.myapp.exception.code;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public class ErrorCode {

    private final int code;
    private final String name;
    private final String message;
}
