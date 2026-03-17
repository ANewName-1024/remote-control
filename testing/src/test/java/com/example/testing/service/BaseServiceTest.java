package com.example.testing.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Service 层基础测试类
 * 提供常用的 Mock 测试方法
 */
@DisplayName("Service 层测试基类")
public abstract class BaseServiceTest<T, ID> {

    @Mock
    protected org.springframework.data.repository.Repository<T, ID> repository;

    protected T entity;
    protected ID entityId;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        entity = createEntity();
        entityId = getEntityId(entity);
    }

    /**
     * 创建测试实体
     */
    protected abstract T createEntity();

    /**
     * 获取实体 ID
     */
    protected abstract ID getEntityId(T entity);

    @Test
    @DisplayName("保存实体")
    void shouldSaveEntity() {
        // Given
        when(repository.save(any(T.class))).thenReturn(entity);

        // When
        T saved = repository.save(entity);

        // Then
        assertThat(saved).isNotNull();
        verify(repository, times(1)).save(any(T.class));
    }

    @Test
    @DisplayName("根据 ID 查询实体")
    void shouldFindById() {
        // Given
        when(repository.findById(entityId)).thenReturn(Optional.of(entity));

        // When
        Optional<T> found = repository.findById(entityId);

        // Then
        assertThat(found).isPresent();
        assertThat(found.get()).isEqualTo(entity);
    }

    @Test
    @DisplayName("查询所有实体")
    void shouldFindAll() {
        // Given
        List<T> entities = List.of(entity);
        when(repository.findAll()).thenReturn(entities);

        // When
        List<T> result = repository.findAll();

        // Then
        assertThat(result).hasSize(1);
        verify(repository, times(1)).findAll();
    }

    @Test
    @DisplayName("删除实体")
    void shouldDeleteEntity() {
        // Given - doNothing for void method
        doNothing().when(repository).deleteById(entityId);

        // When
        repository.deleteById(entityId);

        // Then
        verify(repository, times(1)).deleteById(entityId);
    }

    /**
     * 验证保存时实体 ID 为空
     */
    protected void assertEntityIdIsNullOnSave(T entity) {
        assertThat(entity).satisfies(e -> {
            try {
                var idField = e.getClass().getDeclaredField("id");
                idField.setAccessible(true);
                assertThat(idField.get(e)).isNull();
            } catch (Exception ex) {
                throw new RuntimeException(ex);
            }
        });
    }

    /**
     * 捕获保存的实体
     */
    protected ArgumentCaptor<T> captureSavedEntity() {
        @SuppressWarnings("unchecked")
        ArgumentCaptor<T> captor = ArgumentCaptor.forClass((Class<T>) entity.getClass());
        verify(repository).save(captor.capture());
        return captor;
    }
}
